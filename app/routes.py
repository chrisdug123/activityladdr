from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from .models import User, Event
from . import db
import requests
from datetime import datetime, timedelta
from math import radians, cos, sin, sqrt, atan2
from pytz import timezone, utc
from sqlalchemy import and_


BRISBANE_TZ = timezone('Australia/Brisbane')
main = Blueprint('main', __name__)
city_suburbs = {
    "Sydney": ["Parramatta", "Manly", "Bondi", "Blacktown", "Chatswood", "Liverpool", "Penrith", "Newtown", "Surry Hills", "Castle Hill"],
    "Melbourne": ["St Kilda", "Richmond", "Carlton", "Footscray", "Docklands", "South Yarra", "Fitzroy", "Collingwood", "Hawthorn", "Brunswick"],
    "Brisbane": ["South Brisbane", "Fortitude Valley", "Toowong", "Sunnybank", "Kangaroo Point", "Spring Hill", "Indooroopilly", "Chermside", "Carindale", "Mount Gravatt","Bridgeman Downs","Newstead","Brisbane City"],
    "Perth": ["Fremantle", "Cottesloe", "Subiaco", "Joondalup", "Scarborough", "Claremont", "Northbridge", "Victoria Park", "Leederville", "Midland"],
    "Adelaide": ["Glenelg", "North Adelaide", "Norwood", "Burnside", "Prospect", "Unley", "Semaphore", "Henley Beach", "Mawson Lakes", "Tea Tree Gully"],
}


CITY_TIMEZONES = {
    "Sydney": timezone("Australia/Sydney"),
    "Melbourne": timezone("Australia/Melbourne"),
    "Brisbane": timezone("Australia/Brisbane"),
    "Perth": timezone("Australia/Perth"),
    "Adelaide": timezone("Australia/Adelaide"),
}


def get_coordinates(city, suburb):
    """Fetch latitude and longitude for a given city and suburb using OpenCage Geocoder."""
    API_KEY = "1d38ca059e4648a0bae5b90c7ec49901"  # Replace with your actual API key
    base_url = "https://api.opencagedata.com/geocode/v1/json"
    query = f"{suburb}, {city}, Australia"
    params = {"q": query, "key": API_KEY}
    
    try:
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            results = response.json().get("results")
            if results:
                geometry = results[0]["geometry"]
                return geometry["lat"], geometry["lng"]
            else:
                print(f"No results for query: {query}")
        else:
            print(f"Error from geocoding API: {response.json()}")
    except Exception as e:
        print(f"Error fetching coordinates: {e}")
    return None, None  # Return None if unable to fetch


# Utility function to fetch monthly totals
def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great-circle distance between two points on the Earth."""
    R = 6371  # Earth's radius in kilometers
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c  # Distance in kilometers

def check_event_interactions(activity_id, access_token, buffer_km=5):
    """Determine if an activity interacts with any event based on location and date.
    
    Args:
        activity_id (int): The ID of the Strava activity.
        access_token (str): The Strava access token.
        buffer_km (float): Additional buffer to add to the event radius in kilometers.
    """
    streams = get_activity_streams(activity_id, access_token)
    if not streams or 'latlng' not in streams:
        print(f"Activity {activity_id}: No GPS data available.")
        return False

    latlng_stream = streams['latlng']['data']  # List of GPS points [(lat, lon), ...]

    # Fetch all events
    events = Event.query.all()

    for event in events:
        print(f"Checking event {event.id}: {event.major_city}, {event.suburb}, "
              f"Lat={event.latitude}, Lon={event.longitude}, Radius={event.radius} km")

        # Add buffer to event radius
        effective_radius = event.radius + buffer_km

        for point in latlng_stream:
            lat, lon = point
            distance = haversine(lat, lon, event.latitude, event.longitude)

            print(f"Activity point: Lat={lat}, Lon={lon}, Distance to event={distance:.2f} km, "
                  f"Effective Radius={effective_radius} km")

            if distance <= effective_radius:
                print(f"Interaction found! Activity {activity_id} interacts with Event {event.id}")
                return True  # Interaction found

    print(f"No interaction for Activity {activity_id}")
    return False  # No interaction

@main.route('/all-events', methods=['GET'])
def all_events():
    """Temporary route to display all events."""
    events = Event.query.all()  # Fetch all events from the database

    # Render a template to display the events in a table
    return render_template('all_events.html', events=events)

def get_activity_streams(activity_id, access_token):
    url = f'https://www.strava.com/api/v3/activities/{activity_id}/streams'
    headers = {'Authorization': f'Bearer {access_token}'}
    params = {'keys': 'latlng', 'key_by_type': 'true'}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching activity streams: {response.json()}")
        return None
@main.route('/reset-private-event', methods=['POST'])
def reset_private_event():
    """Reset the private event activation cooldown."""
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Login required"}), 403

    user_id = session['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    # Reset private event cooldown
    user.last_activated = None
    user.private_event_ends = None
    db.session.commit()

    return jsonify({"success": True, "message": "Private event activation reset successfully."})
@main.route('/leaderboard', methods=['GET'])
def leaderboard():
    # Fetch all users sorted by their overall points
    users = User.query.order_by(User.overall_points.desc()).all()

    return render_template('leaderboard.html', users=users)

def calculate_monthly_totals(user_id):
    """Calculate and save monthly totals for the user."""
    user = User.query.get(user_id)
    if not user:
        print(f"User with ID {user_id} not found.")
        return {
            'run': {'distance': 0, 'pace': 0, 'points': 0, 'avg_multiplier': 1},
            'ride': {'distance': 0, 'pace': 0, 'points': 0, 'avg_multiplier': 1},
        }

    access_token = user.strava_access_token
    if not access_token:
        print("No Strava access token found for the user.")
        return {
            'run': {'distance': 0, 'pace': 0, 'points': 0, 'avg_multiplier': 1},
            'ride': {'distance': 0, 'pace': 0, 'points': 0, 'avg_multiplier': 1},
        }

    activities_url = 'https://www.strava.com/api/v3/athlete/activities'
    headers = {'Authorization': f'Bearer {access_token}'}

    # Fetch activities for the current month
    now = datetime.now(BRISBANE_TZ)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_timestamp = int(start_of_month.timestamp())
    end_of_month = (start_of_month + timedelta(days=31)).replace(day=1)  # First day of next month

    events = Event.query.filter(
        and_(Event.date >= start_of_month.date(), Event.date < end_of_month.date())
    ).all()
    # Initialize totals
     # Initialize totals
    totals = {
        'run': {'distance': 0, 'pace': 0, 'points': 0, 'multiplier_sum': 0, 'count': 0},
        'ride': {'distance': 0, 'pace': 0, 'points': 0, 'multiplier_sum': 0, 'count': 0},
    }

    if user.monthly_data is None:
        user.monthly_data = {
            'run': {'distance': 0, 'pace': 0, 'points': 0, 'avg_multiplier': 1},
            'ride': {'distance': 0, 'pace': 0, 'points': 0, 'avg_multiplier': 1},
            }
    overall_points = 0
    try:
        response = requests.get(activities_url, headers=headers, params={'after': start_timestamp})
        if response.status_code != 200:
            print(f"Error fetching activities: {response.json()}")
            return totals

        activities = response.json()
        if not activities:
            print("No activities found for this user.")
            return totals

        for activity in activities:
            activity_type = 'run' if activity['type'] == 'Run' else 'ride'
            distance_km = activity.get('distance', 0) / 1000  # Convert meters to kilometers
            moving_time_hr = activity.get('moving_time', 0) / 3600  # Convert seconds to hours
            pace = distance_km / moving_time_hr if moving_time_hr > 0 else 0
            points=0
            # Default multiplier
            multiplier = 1
            activity_start_time = datetime.fromisoformat(activity.get('start_date_local'))
            activity_date = activity_start_time.date()
            activity_hour = activity_start_time.hour
            # Check for matching events
            matched_event = None
            latlng_stream = get_activity_streams(activity['id'], access_token)
            #print(latlng_stream)
            if latlng_stream and 'latlng' in latlng_stream:
                for event in events:
                    
                    if event.event_type == 'private':
                        print("checking private event")
                        print(f"event start date {event.date}, activity date {activity_date}, event end date {event.date+ timedelta(hours=24)}")
                        # For private events, match by timestamp only
                        if  (event.date == activity_date and event.start_hour <= activity_hour) or(activity_date == (event.date + timedelta(days=1)) and activity_hour < (event.start_hour + 24) % 24):
                            
                            multiplier = 3
                            matched_event = event
                            break
                        if matched_event:
                            print("Private event matched")
                            print(f"Activity {activity['id']} matched event type: {event.event_type} multiplier: {multiplier}")
                            break

                    elif event.event_type == 'public':
                        print("checking public event")
                        print(f"event start date {event.date}, activity date {activity_date}, event end date {event.date+ timedelta(hours=24)}")
                        #
                        event_tz = CITY_TIMEZONES[event.major_city]
                        event_start_time = event_tz.localize(datetime.combine(event.date, datetime.min.time())) + timedelta(hours=event.start_hour)
                        event_end_time = event_start_time + timedelta(hours=3)
                        # For public events, match by time and location
                        
                        if event.latitude is None or event.longitude is None:
                            print(f"Skipping Event {event.id} due to missing coordinates: latitude={event.latitude}, longitude={event.longitude}")
                            continue
                        if event.date != activity_date:
                            continue
                        if not (event_start_time <= activity_hour < event_end_time):
                            continue

                        for point in latlng_stream['latlng']['data']:
                            print(f"Event and Activity date and time match, checking location")
                            lat, lon = point
                            if lat is None or lon is None:
                                continue
                            distance = haversine(lat, lon, event.latitude, event.longitude)
                            if distance <= event.radius:
                                multiplier = 10
                                matched_event = event
                                break
                        
                        if matched_event:
                            print(f"Activity {activity['id']} matched event type: {event.event_type} multiplier: {multiplier}")
                            break

            if activity['type'] == 'Run':
                points = round(pace * distance_km * multiplier)
            if activity['type'] == 'ride':
                points = round(pace * distance_km * multiplier*0.1)
            

            if matched_event:
                print(f"Activity {activity['id']} matched with Event {matched_event.id}. Multiplier = {multiplier}")
            else:
                print(f"Activity {activity['id']} did not match any events.")

            
            overall_points += points  # Add to user's overall points

            # Update totals
            totals[activity_type]['distance'] += distance_km
            totals[activity_type]['pace'] += pace
            totals[activity_type]['points'] += points
            totals[activity_type]['multiplier_sum'] += multiplier
            totals[activity_type]['count'] += 1


        # Finalize averages
        for activity_type in ['run', 'ride']:
            count = totals[activity_type]['count']
            if count > 0:
                if activity_type=='run':
                    totals[activity_type]['pace'] /= count  # Average pace
                    totals[activity_type]['avg_multiplier'] = totals[activity_type]['points'] / (totals[activity_type]['pace']*totals[activity_type]['distance'])  # Average multiplier

        # Save to user model
        #user.monthly_data = totals
        user.overall_points=overall_points
        db.session.commit()
        print(f"user overall points {user.overall_points}")
        return totals

    except Exception as e:
        print(f"Error calculating monthly totals: {e}")
        return totals

# Utility function to fetch past year totals


def get_past_year_totals(access_token):
    """Fetch monthly totals for the past year, applying multipliers based on activity interactions."""
    activities_url = 'https://www.strava.com/api/v3/athlete/activities'
    headers = {'Authorization': f'Bearer {access_token}'}
    past_year_totals = []
    today = datetime.now()

    for month_offset in range(12):
        # Calculate start and end timestamps for each month
        month_start = datetime(today.year, today.month, 1) - timedelta(days=30 * month_offset)
        month_end = datetime(month_start.year, month_start.month, 1) + timedelta(days=31)
        month_start_timestamp = int(month_start.timestamp())
        month_end_timestamp = int(month_end.timestamp())

        # Initialize totals for this month
        totals = {
            'month': month_start.strftime('%B %Y'),
            'run': {'distance': 0, 'time': 0, 'points': 0, 'multiplier_sum': 0, 'count': 0},
            'ride': {'distance': 0, 'time': 0, 'points': 0, 'multiplier_sum': 0, 'count': 0},
            'total_points': 0,
            'avg_multiplier': 1.0,  # Default average multiplier
        }

        try:
            # Fetch activities for the given month
            response = requests.get(activities_url, headers=headers, params={
                'after': month_start_timestamp,
                'before': month_end_timestamp
            })
            if response.status_code != 200:
                print(f"Error fetching activities for {totals['month']}: {response.json()}")
                continue

            activities = response.json()

            for activity in activities:
                activity_type = 'run' if activity['type'] == 'Run' else 'ride'
                distance_km = activity.get('distance', 0) / 1000  # Convert meters to kilometers
                moving_time_hr = activity.get('moving_time', 0) / 3600  # Convert seconds to hours
                pace = distance_km / moving_time_hr if moving_time_hr > 0 else 0

                multiplier = 1
                latlng_stream = get_activity_streams(activity['id'], access_token)
                if not latlng_stream or 'latlng' not in latlng_stream or not latlng_stream['latlng']['data']:
                    print(f"Activity {activity['id']} has no valid GPS data.")
                    continue

                # Parse activity time
                activity_start_time = datetime.fromisoformat(activity.get('start_date_local'))
                activity_date = activity_start_time.date()
                activity_hour = activity_start_time.hour

                for event in events:
                    # Filter by date and time first
                    if event.date != activity_date:
                        continue

                    event_end_hour = (event.start_hour + 3) % 24  # Wrap around for midnight
                    if not (event.start_hour <= activity_hour < event_end_hour):
                        continue  # Skip if the activity is outside the event's time range

                    # Now check location interactions
                    for point in latlng_stream['latlng']['data']:
                        lat, lon = point
                        if lat is None or lon is None:
                            print(f"Skipping point with missing coordinates: lat={lat}, lon={lon}")
                            continue

                        distance = haversine(lat, lon, event.latitude, event.longitude)
                        if distance <= event.radius:
                            multiplier = event.get_multiplier(user)
                            print(f"Activity {activity['id']} matched with Event {event.id}. Multiplier = {multiplier}")
                            break

                    # Break early if a matching event is found
                    if multiplier > 1:
                        break

                points = round(pace * distance_km * multiplier)

                # Update totals
                totals[activity_type]['distance'] += distance_km
                totals[activity_type]['pace'] += pace
                totals[activity_type]['points'] += points
                totals[activity_type]['multiplier_sum'] += multiplier
                totals[activity_type]['count'] += 1


            # Finalize totals for the month
            for key in ['run', 'ride']:
                distance = totals[key]['distance']
                time = totals[key]['time'] / 3600  # Convert seconds to hours
                totals[key]['pace'] = distance / time if time > 0 else 0
                totals[key]['points'] = round(3 * totals[key]['pace'] * distance) if key == 'run' else round(totals[key]['pace'] * distance)
                totals[key]['avg_multiplier'] = (totals[key]['multiplier_sum'] / totals[key]['count']) if totals[key]['count'] > 0 else 1.0

            # Calculate total points and average multiplier for the month
            totals['total_points'] = totals['run']['points'] + totals['ride']['points']
            totals['avg_multiplier'] = (
                (totals['run']['multiplier_sum'] + totals['ride']['multiplier_sum']) /
                (totals['run']['count'] + totals['ride']['count'])
            ) if (totals['run']['count'] + totals['ride']['count']) > 0 else 1.0

        except Exception as e:
            print(f"Error fetching monthly totals for {totals['month']}: {e}")

        past_year_totals.append(totals)

    # Return past year totals in chronological order
    return past_year_totals[::-1]

# Home page route
@main.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('main.account'))  # Redirect to account if logged in
    return redirect(url_for('main.login'))  # Redirect to login otherwise

# Login route
@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('Login successful!', 'success')
            return redirect(url_for('main.account'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

# Logout route
@main.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.login'))

# Create account route
@main.route('/create-account', methods=['GET', 'POST'])
def create_account():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'warning')
            return redirect(url_for('main.login'))
        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully!', 'success')
        return redirect(url_for('main.login'))
    return render_template('create_account.html')


@main.route('/delete-all-events', methods=['POST','GET'])
def delete_all_events():
    """Delete all events for the logged-in user."""
    if 'user_id' not in session:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('main.login'))

    user_id = session['user_id']

    try:
        # Delete all events associated with the user
        Event.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        flash('All events have been successfully deleted.', 'success')
    except Exception as e:
        flash('An error occurred while deleting events. Please try again.', 'danger')
        print(f"Error deleting events: {e}")  # Debug

    return redirect(url_for('main.schedule'))
@main.route('/delete-user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    """Route to delete a specific user by their ID."""
    #if 'admin' not in session:  # Ensure only admins can delete users
    #    flash('Unauthorized access.', 'danger')
    #    return redirect(url_for('main.index'))

    user = User.query.get(user_id)
    if not user:
        flash(f"User with ID {user_id} not found.", "warning")
        return redirect(url_for('main.manage_users'))

    try:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.email} deleted successfully.", "success")
    except Exception as e:
        print(f"Error deleting user {user_id}: {e}")
        flash("An error occurred while trying to delete the user.", "danger")

    return redirect(url_for('main.manage_users'))
@main.route('/manage-users', methods=['GET'])
def manage_users():
    """Route to display a list of all users for admin management."""
    #if 'admin' not in session:  # Ensure only admins can manage users
    #    flash('Unauthorized access.', 'danger')
    #    return redirect(url_for('main.index'))

    users = User.query.all()
    return render_template('manage_users.html', users=users)


# Account page route

@main.route('/account')
def account():
    """Render the account page."""
    if 'user_id' not in session:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('main.login'))

    user_id = session['user_id']
    user = User.query.get(user_id)

    if not user:
        flash('User not found. Please log in again.', 'danger')
        return redirect(url_for('main.login'))

    now_brisbane = datetime.now(BRISBANE_TZ)

    # Private event status and cooldown calculations
    private_event_active = user.private_event_active()
    can_activate = user.can_activate()
    private_event_ends = user.private_event_ends.astimezone(BRISBANE_TZ).isoformat() if user.private_event_ends else None
    next_activation_time = (user.last_activated + timedelta(days=7)).astimezone(BRISBANE_TZ).isoformat() if user.last_activated else None
    
        # Calculate bucks regeneration countdown
    bucks_reset_time = None
    if user.last_bucks_update:
        # Calculate next regeneration time
        next_regeneration_time = user.last_bucks_update + timedelta(weeks=1)
        now_utc = datetime.utcnow()
        if next_regeneration_time > now_utc:
            bucks_reset_time = int((next_regeneration_time - now_utc).total_seconds())  # Time left in seconds
        else:
            bucks_reset_time = 0  # Bucks should already be regenerated
    print(bucks_reset_time)
    # Load cached monthly_data directly from the user model
    totals = user.monthly_data or {
        'run': {'distance': 0, 'pace': 0, 'points': 0, 'avg_multiplier': 1},
        'ride': {'distance': 0, 'pace': 0, 'points': 0, 'avg_multiplier': 1},
    }

    return render_template(
        'account.html',
        user=user,
        private_event_active=private_event_active,
        can_activate=can_activate,
        private_event_ends=private_event_ends,
        next_activation_time=next_activation_time,
        bucks_reset_time=bucks_reset_time,
        totals=totals
    )



@main.route('/refresh-data', methods=['POST'])
def refresh_data():
    """Endpoint to refresh monthly totals for the logged-in user."""
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Login required"}), 403

    user_id = session['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({"success": False, "message": "User not found."}), 404

    try:
        # Recalculate monthly totals and update user data
        monthly_totals = calculate_monthly_totals(user_id)
        user.monthly_data = monthly_totals  # Cache the new totals
        user.monthly_last_updated = datetime.utcnow()  # Track when it was last updated
        db.session.commit()

        return jsonify({"success": True, "message": "Monthly totals refreshed successfully!", "totals": monthly_totals})
    except Exception as e:
        print(f"Error refreshing monthly totals: {e}")
        return jsonify({"success": False, "message": "Error refreshing monthly totals."}), 500

@main.route('/activate-private-event', methods=['POST'])
def activate_private_event():
    """Activate a private event for the user."""
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Login required"}), 403

    user_id = session['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    # Get the current time in Brisbane timezone
    now_brisbane = datetime.now(BRISBANE_TZ)

    # Check cooldown
    if user.last_activated:
        # Convert last activation to Brisbane timezone
        last_activated_brisbane = (
            BRISBANE_TZ.localize(user.last_activated)
            if user.last_activated.tzinfo is None
            else user.last_activated.astimezone(BRISBANE_TZ)
        )
        next_activation_brisbane = last_activated_brisbane + timedelta(days=7)

        if now_brisbane < next_activation_brisbane:
            # Calculate remaining time
            time_left = (next_activation_brisbane - now_brisbane).total_seconds()
            days, remainder = divmod(int(time_left), 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            return jsonify({
                "success": False,
                "message": f"Cannot activate until cooldown ends. Time left: {days}d {hours}h {minutes}m {seconds}s"
            }), 400

    # Check if the user has enough bucks
    user = User.query.get(user_id)
    cost=5
    if user.bucks < cost:
        return jsonify({"success": False, "message": f"Insufficient bucks. You need {cost} bucks."}), 400

    # Deduct bucks and create the event
    user.bucks -= cost
    # Create a private event
    #now_utc = datetime.utcnow()  # UTC time for database consistency
    private_event = Event(
        user_id=user.id,
        major_city="Private",  # Indicate this is a private event
        suburb="N/A",
        event_type="private",
        date=now_brisbane.date(),
        start_hour=now_brisbane.hour,
        latitude=None,  # Private events might not have a location
        longitude=None,
        radius=0.0
    )
    db.session.add(private_event)

    # Update user's private event tracking
    user.private_event_ends = now_brisbane + timedelta(hours=24)  # Store in UTC
    user.last_activated = now_brisbane  # Store activation time in UTC
    db.session.commit()

    return jsonify({"success": True, "message": "Private event activated for the next 24 hours."})

@main.route('/schedule', methods=['GET'])
def schedule():
    if 'user_id' not in session:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('main.login'))

    user_id = session['user_id']
    major_city_filter = request.args.get('major_city','Brisbane')

    if not major_city_filter or major_city_filter not in CITY_TIMEZONES:
        flash('Please select a valid major city.', 'warning')
        return redirect(url_for('main.schedule'))

    # Get the time zone for the selected city
    city_tz = CITY_TIMEZONES[major_city_filter]

    # Query events for the selected city
    events_query = Event.query.filter(Event.user_id != None)
    events_query = events_query.filter(Event.major_city == major_city_filter)
    events = events_query.all()

    # Localized current time in the selected city
    now_utc = datetime.utcnow()
    now_city = utc.localize(now_utc).astimezone(city_tz)
    today_city = now_city.date()
    current_hour_city = now_city.hour

    valid_times = range(0, 24, 3)

    # Limit calendar to 7 days
    calendar = {}
    for offset in range(5):  # Show only the next 7 days
        date = today_city + timedelta(days=offset)
        calendar[date] = {}

        for hour in valid_times:
            booked_event = next((e for e in events if e.date == date and e.start_hour == hour), None)
            if booked_event:
                event_user = User.query.get(booked_event.user_id)
                calendar[date][hour] = {
                    'status': 'booked',
                    'suburb': booked_event.suburb,
                    'multiplier': booked_event.get_multiplier(event_user),
                    'user': {
                        'first_name': event_user.first_name,
                        'last_name': event_user.last_name
                    }
                }
            elif date == today_city and hour + 3 <= current_hour_city:
                calendar[date][hour] = {'status': 'unavailable'}
            else:
                # Calculate cost based on days ahead
                days_ahead = (date - today_city).days
                cost = 0 if days_ahead <= 1 else days_ahead - 1
                calendar[date][hour] = {
                    'status': 'available',
                    'cost': cost
                }

    return render_template(
        'schedule.html',
        calendar=calendar,
        cities=CITY_TIMEZONES.keys(),
        selected_city=major_city_filter
    )

@main.route('/book-slot', methods=['POST'])
def book_slot():
    """Book a public slot through the calendar."""
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Login required"}), 403

    data = request.json

    # Extract and validate `date`
    date_string = data.get('date', '').strip()
    if not date_string:
        return jsonify({"success": False, "message": "Date is missing."}), 400
    try:
        date = datetime.strptime(date_string, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"success": False, "message": f"Invalid date format: {date_string}. Expected format: YYYY-MM-DD."}), 400

    # Extract and validate `hour`
    try:
        hour = int(data.get('hour', -1))  # Default to an invalid hour (-1)
        if hour not in range(0, 24, 3):  # Only valid 3-hour slots (e.g., 0, 3, 6, ..., 21)
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid or missing hour. Must be 0, 3, 6, ..., 21."}), 400

    # Extract other fields
    major_city = data.get('major_city')
    suburb = data.get('suburb')
    user_id = session['user_id']

    if not major_city or major_city not in CITY_TIMEZONES:
        return jsonify({"success": False, "message": "Invalid or missing major city."}), 400

    if not suburb:
        return jsonify({"success": False, "message": "Suburb is missing."}), 400

    # Calculate timezone-aware current date and time
    city_tz = CITY_TIMEZONES[major_city]
    now_utc = datetime.utcnow()
    now_city = utc.localize(now_utc).astimezone(city_tz)
    today_city = now_city.date()

    # Calculate the cost based on days ahead
    days_ahead = (date - today_city).days
    cost = 0 if days_ahead <= 1 else days_ahead - 1

    latitude, longitude = get_coordinates(major_city, suburb)
    if latitude is None or longitude is None:
        flash('Unable to fetch coordinates for the location. Please try again.', 'danger')
        return redirect(url_for('main.events'))
    # Validate the selected date and time
    if date < today_city or (date == today_city and hour + 3 <= now_city.hour):
        return jsonify({"success": False, "message": "Invalid date or time."}), 400

    # Check if the slot is already booked
    if Event.query.filter_by(date=date, start_hour=hour, major_city=major_city).first():
        return jsonify({"success": False, "message": "Slot already booked in this city."}), 400

    # Fetch the user and validate bucks
    user = User.query.get(user_id)
    if user is None:
        return jsonify({"success": False, "message": "User not found."}), 404

    if user.bucks < cost:
        return jsonify({"success": False, "message": f"Insufficient bucks. You need {cost} bucks."}), 400

    # Deduct bucks and create the event
    user.bucks -= cost
    new_event = Event(
        user_id=user_id,
        major_city=major_city,
        suburb=suburb,
        date=date,
        start_hour=hour,
        event_type='public',
        latitude=latitude,
        longitude=longitude
    )
    db.session.add(new_event)
    db.session.commit()

    return jsonify({"success": True, "message": "Slot booked successfully!"})


@main.route('/events', methods=['GET', 'POST'])
def events():
    """Create a new event or view the event creation form."""
    if 'user_id' not in session:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('main.login'))

    if request.method == 'POST':
        event_type = request.form['event_type']  # New dropdown for event type
        major_city = request.form['major_city']
        suburb = request.form['suburb']
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        start_hour = int(request.form['hour'])  # Start of the 3-hour time slot
        user_id = session['user_id']

        # Determine cost based on event type
        cost = 5 if event_type == 'community' else 3

        user = User.query.get(user_id)
        if user.bucks < cost:
            flash('Insufficient bucks to create this event.', 'danger')
            return redirect(url_for('main.events'))

         # Fetch coordinates for the event
        latitude, longitude = get_coordinates(major_city, suburb)
        if latitude is None or longitude is None:
            flash('Unable to fetch coordinates for the location. Please try again.', 'danger')
            return redirect(url_for('main.events'))
        # Deduct bucks
        user.bucks -= cost

        # Create the event
        new_event = Event(
            user_id=user_id if event_type == 'personal' else None,  # Only set user_id for personal events
            major_city=major_city,
            suburb=suburb,
            event_type=event_type,
            date=date,
            start_hour=start_hour,
            latitude=latitude,
            longitude=longitude
        )
        db.session.add(new_event)
        db.session.commit()

        flash('Event created successfully!', 'success')
        return redirect(url_for('main.schedule'))

    return render_template('events.html', cities=city_suburbs)


@main.route('/how-it-works', methods=['GET'])
def how_it_works():
    """Render the How It Works page."""
    return render_template('how_it_works.html')


@main.route('/valid-dates')
def valid_dates():
    """Return a JSON list of valid dates (today and tomorrow) in Brisbane time."""
    # Set Brisbane timezone
    brisbane_tz = timezone('Australia/Brisbane')

    # Get current time in UTC and convert to Brisbane time
    now_utc = datetime.utcnow()
    now_brisbane = utc.localize(now_utc).astimezone(brisbane_tz)

    # Get today's and tomorrow's dates in Brisbane time
    today_brisbane = now_brisbane.date()
    tomorrow_brisbane = today_brisbane + timedelta(days=1)

    valid_dates = [
        {"value": today_brisbane.strftime('%Y-%m-%d'), "label": today_brisbane.strftime('%A, %d %B %Y')},
        {"value": tomorrow_brisbane.strftime('%Y-%m-%d'), "label": tomorrow_brisbane.strftime('%A, %d %B %Y')}
    ]

    return jsonify(valid_dates)
from pytz import timezone
from datetime import datetime, timedelta

@main.route('/available-timeslots')
def available_timeslots():
    """Return a JSON list of available 3-hour time slots for the selected date in Brisbane time."""
    selected_date = request.args.get('date')
    if not selected_date:
        return jsonify([])

    # Parse the selected date
    brisbane_tz = timezone('Australia/Brisbane')
    # Get current time in UTC and convert to Brisbane time
    now_utc = datetime.utcnow()
    now_brisbane = utc.localize(now_utc).astimezone(brisbane_tz)
    selected_date_brisbane = datetime.strptime(selected_date, '%Y-%m-%d').date()

    # Retrieve booked slots
    booked_slots = Event.query.filter_by(date=selected_date_brisbane).all()
    booked_hours = {event.start_hour for event in booked_slots}

    # Calculate available time slots
    available_slots = []
    print("timeslots")
    for hour in range(0, 24, 3):  # Loop through each 3-hour slot
        slot_start = brisbane_tz.localize(datetime.combine(selected_date_brisbane, datetime.min.time()) + timedelta(hours=hour))
        slot_end = slot_start + timedelta(hours=3)

        # Skip slots that are already fully passed today
        if selected_date_brisbane == now_brisbane.date() and slot_end <= now_brisbane:
            continue
        print(selected_date_brisbane)
        print(now_brisbane.date())
        print("slot end", slot_end)
        
        print("now brisbane", now_brisbane)
        # Skip slots that are fully booked
        if any(h in booked_hours for h in range(hour, hour + 3)):
            continue

        # Add the slot to the available list
        available_slots.append({
            'hour': hour,
            'start_time': slot_start.strftime('%H:%M'),
            'end_time': slot_end.strftime('%H:%M')
        })

    return jsonify(available_slots)


def fetch_user_activities(user):
    """Fetch the user's activities from Strava."""
    if user.strava_expires_at and datetime.now().timestamp() > user.strava_expires_at:
        refresh_strava_token(user)  # Refresh token if expired

    headers = {'Authorization': f'Bearer {user.strava_access_token}'}
    url = 'https://www.strava.com/api/v3/athlete/activities'

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch activities: {response.json()}")
        return []

@main.route('/suburbs/<city>')
def get_suburbs(city):
    """Return a JSON list of suburbs for the selected city."""
    suburbs = city_suburbs.get(city, [])
    return jsonify(suburbs)

def refresh_strava_token(user):
    """Refresh the Strava access token using the user's refresh token."""
    token_url = current_app.config['STRAVA_TOKEN_URL']
    client_id = current_app.config['STRAVA_CLIENT_ID']
    client_secret = current_app.config['STRAVA_CLIENT_SECRET']

    try:
        response = requests.post(token_url, data={
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': user.strava_refresh_token
        })

        if response.status_code == 200:
            data = response.json()
            user.strava_access_token = data['access_token']
            user.strava_refresh_token = data['refresh_token']
            user.strava_expires_at = data['expires_at']
            db.session.commit()
            return user.strava_access_token
        else:
            print(f"Failed to refresh token for user {user.id}: {response.json()}")
    except Exception as e:
        print(f"Exception while refreshing token: {e}")

    return None

# Link Strava account route
@main.route('/link-strava')
def link_strava():
    """Start the Strava OAuth flow for the logged-in user."""
    if 'user_id' not in session:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('main.login'))

    # Dynamically fetch client_id from configuration
    client_id = current_app.config.get('STRAVA_CLIENT_ID')
    if not client_id:
        flash('Strava integration is not configured properly.', 'danger')
        return redirect(url_for('main.account'))

    redirect_uri = url_for('main.strava_callback', _external=True)
    scope = "read,activity:read"  # Scopes for Strava access
    auth_url = (
        f"{current_app.config['STRAVA_AUTH_URL']}?client_id={client_id}"
        f"&response_type=code&redirect_uri={redirect_uri}&scope={scope}"
    )

    print(f"Redirecting to Strava Auth URL: {auth_url}")  # Debugging

    return redirect(auth_url)

# Strava callback route
@main.route('/strava/callback')
def strava_callback():
    """Handle Strava OAuth callback and store user-specific tokens."""
    if 'user_id' not in session:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('main.login'))

    code = request.args.get('code')
    if not code:
        flash('Authorization failed. Please try again.', 'danger')
        return redirect(url_for('main.account'))

    client_id = current_app.config.get('STRAVA_CLIENT_ID')
    client_secret = current_app.config.get('STRAVA_CLIENT_SECRET')
    token_url = current_app.config.get('STRAVA_TOKEN_URL')

    if not client_id or not client_secret or not token_url:
        flash('Strava integration is not configured properly.', 'danger')
        return redirect(url_for('main.account'))

    response = requests.post(token_url, data={
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code'
    })

    if response.status_code == 200:
        data = response.json()
        user = User.query.get(session['user_id'])

        user.strava_id = data.get('athlete', {}).get('id')
        user.strava_access_token = data.get('access_token')
        user.strava_refresh_token = data.get('refresh_token')
        user.strava_expires_at = data.get('expires_at')

        db.session.commit()
        flash('Strava account linked successfully!', 'success')
    else:
        flash('Failed to link Strava account. Please try again.', 'danger')

    return redirect(url_for('main.account'))
