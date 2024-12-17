from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from .models import User, Event
from . import db
import requests
from datetime import datetime, timedelta
from math import radians, cos, sin, sqrt, atan2
from pytz import timezone, utc
from sqlalchemy import and_
from datetime import datetime
from dateutil.parser import isoparse

BRISBANE_TZ = timezone('Australia/Brisbane')
main = Blueprint('main', __name__)


STATE_TIMEZONES = {
    "Queensland": "Australia/Brisbane",
    "New South Wales": "Australia/Sydney",
    "Victoria": "Australia/Melbourne",
    "Western Australia": "Australia/Perth",
}

import requests

import requests

import requests

import requests

def fetch_suburbs_by_state(state_name):
    """Fetch all suburbs within a state using Overpass API."""
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    area["name"="{state_name}"]->.searchArea;
    (nwr["place"="suburb"](area.searchArea););
    out body;
    """
    try:
        response = requests.post(overpass_url, data={"data": query})
        if response.status_code == 200:
            results = response.json().get("elements", [])
            suburbs = set()
            for element in results:
                name = element.get("tags", {}).get("name")
                if name:
                    suburbs.add(name)
            print(suburbs)
            return sorted(suburbs)  # Return unique, sorted list of suburbs
        else:
            print(f"Error fetching suburbs: {response.status_code}")
    except Exception as e:
        print(f"API request failed: {e}")
    return []


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
    users = User.query.order_by(User.overall_points.desc()).all()

    # Calculate countdown to end of  the month
    now = datetime.now()
    first_day_next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    end_of_month = first_day_next_month - timedelta(seconds=1)
    countdown = (end_of_month - now).total_seconds()

    # Prepare data for the pie chart
    chart_labels = [user.username for user in users]
    chart_data = [user.overall_points for user in users]

    return render_template(
        'leaderboard.html',
        users=users,
        countdown=countdown,
        chart_labels=chart_labels,
        chart_data=chart_data
    )

def calculate_monthly_totals(user_id):
    """Calculate and save monthly totals for the user."""
    user = User.query.get(user_id)
    if not user:
        print(f"User with ID {user_id} not found.")
        return {
            'run': {'distance': 0, 'time': 0, 'pace': 0, 'points': 0, 'avg_distance': 0, 'avg_multiplier': 0, 'count': 0},
            'ride': {'distance': 0, 'time': 0, 'pace': 0, 'points': 0, 'avg_distance': 0, 'avg_multiplier': 0, 'count': 0},
        }

    access_token = user.strava_access_token
    if not access_token:
        print("No Strava access token found for the user.")
        return {}

    activities_url = 'https://www.strava.com/api/v3/athlete/activities'
    headers = {'Authorization': f'Bearer {access_token}'}

    now = datetime.now(BRISBANE_TZ)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_timestamp = int(start_of_month.timestamp())

    # Fetch all events for this month
    events = Event.query.filter(Event.date >= start_of_month.date()).all()

    # Totals initialization
    totals = {
        'run': {'distance': 0, 'time': 0, 'points': 0, 'multiplier_sum': 0, 'count': 0},
        'ride': {'distance': 0, 'time': 0, 'points': 0, 'multiplier_sum': 0, 'count': 0},
    }
    overall_points = 0

    try:
        response = requests.get(activities_url, headers=headers, params={'after': start_timestamp})
        if response.status_code != 200:
            print(f"Error fetching activities: {response.json()}")
            return totals

        activities = response.json()
        for activity in activities:
            # Determine activity type
            print(f"\nChecking Activity ID: {activity['id']}")

            activity_type = 'run' if activity['type'] == 'Run' else 'ride'
            distance_km = activity.get('distance', 0) / 1000  # Convert to kilometers
            time_hr = activity.get('moving_time', 0) / 3600  # Convert moving time to hours
            if distance_km == 0 or time_hr == 0:
                continue  # Skip invalid activities

            pace = distance_km / time_hr if time_hr > 0 else 0  # Pace = Distance / Time
            multiplier = 1  # Default multiplier
            matched_event = None
            activity_start_time = isoparse(activity.get('start_date_local'))
            activity_date = activity_start_time.date()
            activity_hour = activity_start_time.hour

            # Fetch activity GPS data for location matching
            latlng_stream = get_activity_streams(activity['id'], access_token)
            print(f"Activity Date: {activity_date}, Hour: {activity_hour}")
            print(f"Distance: {distance_km} km, Time: {time_hr} hr, Pace: {pace:.2f}")

            # Check for event interactions
            if latlng_stream and 'latlng' in latlng_stream:
                for event in events:
                    
                    if event.event_type == 'private':
                        if (event.date == activity_date and event.start_hour <= activity_hour) or \
                           (activity_date == (event.date + timedelta(days=1)) and activity_hour < (event.start_hour + 24) % 24):
                            multiplier = 3
                            matched_event = event
                            break
                    elif event.event_type == 'public':
                        print(f"Checking Event ID: {event.id}, Date: {event.date}, Hour: {event.start_hour}")
                        event_tz = timezone(STATE_TIMEZONES.get(event.major_city, "Australia/Brisbane"))
                        event_start_time = event_tz.localize(datetime.combine(event.date, datetime.min.time())) + timedelta(hours=event.start_hour)
                        event_end_time = event_start_time + timedelta(hours=3)

                        if event.date == activity_date and event_start_time.hour <= activity_hour < event_end_time.hour:
                            print("Date matches")
                            interaction_found = check_event_interactions(activity['id'], access_token, buffer_km=5)
                            if interaction_found:
                                multiplier = 10  # Event interaction multiplier
                                matched_event = event
                                print(f"Activity {activity['id']} interacted with an event. Multiplier = {multiplier}")

                        if matched_event:
                            break

            # Calculate points
            if activity_type == 'run':
                points = round(pace * distance_km * multiplier)
            else:  # 'ride' activities
                points = round(pace * distance_km * multiplier * 0.1)

            # Update totals
            totals[activity_type]['distance'] += distance_km
            totals[activity_type]['time'] += time_hr
            totals[activity_type]['points'] += points
            totals[activity_type]['multiplier_sum'] += multiplier
            totals[activity_type]['count'] += 1
            overall_points += points

        # Finalize averages
        for activity_type in ['run', 'ride']:
            count = totals[activity_type]['count']
            if count > 0:
                totals[activity_type]['pace'] = totals[activity_type]['distance'] / totals[activity_type]['time']  # Average pace (km/h)
                totals[activity_type]['avg_distance'] = totals[activity_type]['distance'] / count
                totals[activity_type]['avg_multiplier'] = totals[activity_type]['multiplier_sum'] / count
            else:
                totals[activity_type]['pace'] = 0
                totals[activity_type]['avg_distance'] = 0
                totals[activity_type]['avg_multiplier'] = 0

        # Update user data
        user.monthly_data = totals
        user.overall_points = overall_points
        user.monthly_last_updated = datetime.utcnow()
        db.session.commit()
        print(f"Final Overall Points: {user.overall_points}")
        return totals

    except Exception as e:
        print(f"Error calculating monthly totals: {e}")
        return totals


@main.route('/refresh-data', methods=['POST'])
def refresh_data():
    """Refresh monthly totals for the logged-in user."""
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Login required"}), 403

    user_id = session['user_id']
    user = User.query.get(user_id)

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    try:
        totals = calculate_monthly_totals(user_id)
        user.monthly_data = totals  # Cache the totals
        user.monthly_last_updated = datetime.utcnow()  # Update the last refresh timestamp
        db.session.commit()

        return jsonify({"success": True, "message": "Monthly totals refreshed!", "totals": totals})
    except Exception as e:
        print(f"Error refreshing monthly totals: {e}")
        return jsonify({"success": False, "message": "Error refreshing data"}), 500


# Utility function to fetch past year totals

@main.route('/test-suburb-coordinates', methods=['GET'])
def test_suburb_coordinates():
    """
    Test route: Loop through all suburbs for each state, fetch coordinates,
    and check if they are valid. Display results in a table.
    """
    from . import db  # Ensure this is available
    results = []

    # List of states to test
    states = ["Queensland", "New South Wales", "Victoria", "Western Australia"]

    # Loop through each state and its suburbs
    for state in states:
        print(f"Fetching suburbs for {state}")
        suburbs = fetch_suburbs_by_state(state)  # Fetch suburbs dynamically
        if not suburbs:
            print(f"No suburbs found for state: {state}")
            continue

        for suburb in suburbs:
            # Fetch coordinates for each suburb
            latitude, longitude = get_coordinates(state, suburb)
            print(f"State: {state}, Suburb: {suburb}, Lat: {latitude}, Lon: {longitude}")

            # Append results to display later
            results.append({
                "state": state,
                "suburb": suburb,
                "latitude": latitude if latitude else "Missing",
                "longitude": longitude if longitude else "Missing"
            })

    # Render results in a sortable table
    return render_template('test_suburb_coordinates.html', results=results)

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
                if distance_km > 0 and moving_time_hr > 0:
                # Calculate speed in km/h for both run and ride
                    speed_kmh = distance_km / moving_time_hr
                    totals[activity_type]['pace'] += speed_kmh  # Sum speeds


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
                totals[activity_type]['time'] += moving_time_hr
                totals[activity_type]['points'] += points
                totals[activity_type]['multiplier_sum'] += multiplier
                totals[activity_type]['count'] += 1

                for activity_type in ['run', 'ride']:
                    count = totals[activity_type]['count']
                    if count > 0:
                        totals[activity_type]['pace'] /= count  # Average speed in km/h

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
        dob = request.form['dob']
        username = request.form['username']  # New field
        email = request.form['email']
        password = request.form['password']

        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'warning')
            return redirect(url_for('main.create_account'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'warning')
            return redirect(url_for('main.create_account'))

        # Create the new user
        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            username=username,
            monthly_data={
            'run': {'distance': 0, 'time': 0, 'pace': 0, 'points': 0, 'avg_distance': 0, 'avg_multiplier': 0, 'count': 0},
            'ride': {'distance': 0, 'time': 0, 'pace': 0, 'points': 0, 'avg_distance': 0, 'avg_multiplier': 0, 'count': 0},
        }  # Save username
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

    
    try:
        # Delete all events associated with the user
        Event.query.delete()
        User.query.delete()
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
    print(user.monthly_data)
    totals = user.monthly_data or {
            'run': {'distance': 0, 'time': 0, 'pace': 0, 'points': 0, 'avg_distance': 0, 'avg_multiplier': 0, 'count': 0},
            'ride': {'distance': 0, 'time': 0, 'pace': 0, 'points': 0, 'avg_distance': 0, 'avg_multiplier': 0, 'count': 0},
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

from pytz import timezone
import pytz  # For UTC handling

# Mapping states to their respective timezones
STATE_TIMEZONES = {
    "Queensland": "Australia/Brisbane",
    "New South Wales": "Australia/Sydney",
    "Victoria": "Australia/Melbourne",
    "Western Australia": "Australia/Perth",
}

@main.route('/schedule', methods=['GET'])
def schedule():
    if 'user_id' not in session:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('main.login'))

    # Fetch the selected state (default to Queensland)
    state_filter = request.args.get('state', 'Queensland')

    if state_filter not in STATE_TIMEZONES:
        flash('Invalid state selected.', 'danger')
        return redirect(url_for('main.schedule'))

    # Get the timezone for the selected state
    state_tz = timezone(STATE_TIMEZONES[state_filter])

    # Current time in the state's timezone
    now_utc = datetime.utcnow()
    now_state = pytz.utc.localize(now_utc).astimezone(state_tz)
    today = now_state.date()
    current_hour = now_state.hour

    # Query all events for the selected state
    events = Event.query.filter(Event.major_city == state_filter).all()

    # Define valid times (3-hour slots)
    valid_times = range(3, 24, 3)

    # Build calendar
    calendar = {}
    for offset in range(4):  # Next 5 days
        date = today + timedelta(days=offset)
        calendar[date] = {}

        for hour in valid_times:
            # Check if the slot is booked
            booked_event = next((e for e in events if e.date == date and e.start_hour == hour), None)
            if booked_event:
                calendar[date][hour] = {
                    'status': 'booked',
                    'suburb': booked_event.suburb,
                    'username': User.query.get(booked_event.user_id).username
                }
            else:
                # Mark slots as unavailable only if they are past and not booked
                if date == today and hour + 3 <= current_hour:
                    calendar[date][hour] = {'status': 'unavailable'}
                else:
                    # Slot is available: calculate cost based on days ahead
                    days_ahead = (date - today).days
                    cost = 0 if days_ahead <= 1 else min(days_ahead - 1, 5)  # Cap cost at 5 bucks

                    calendar[date][hour] = {
                        'status': 'available',
                        'cost': cost
                    }

    return render_template(
        'schedule.html',
        calendar=calendar,
        states=STATE_TIMEZONES.keys(),  # Pass states to the template
        selected_state=state_filter
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
        return jsonify({"success": False, "message": "Invalid date format."}), 400

    # Extract and validate `hour`
    try:
        hour = int(data.get('hour', -1))  # Default to an invalid hour (-1)
        if hour not in range(0, 24, 3):  # Only valid 3-hour slots (e.g., 0, 3, 6, ..., 21)
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid or missing hour. Must be 0, 3, 6, ..., 21."}), 400

    # Extract other fields
    state = data.get('state')  # State selected by the user
    suburb = data.get('suburb')  # Suburb selected by the user
    user_id = session['user_id']

    # Validate state
    if not state or state not in STATE_TIMEZONES:
        return jsonify({"success": False, "message": "Invalid or missing state."}), 400

    # Validate suburb
    if not suburb:
        return jsonify({"success": False, "message": "Suburb is missing."}), 400

    # Get timezone-aware current time for the selected state
    state_tz = timezone(STATE_TIMEZONES[state])
    now_utc = datetime.utcnow()
    now_state = pytz.utc.localize(now_utc).astimezone(state_tz)
    today_state = now_state.date()

    # Fetch coordinates dynamically for the suburb
    latitude, longitude = get_coordinates(state, suburb)
    if latitude is None or longitude is None:
        return jsonify({"success": False, "message": "Unable to fetch coordinates for the location. Please try again."}), 400

    # Validate the selected date and time
    if date < today_state or (date == today_state and hour + 3 <= now_state.hour):
        return jsonify({"success": False, "message": "Invalid date or time."}), 400

    # Calculate the cost based on days ahead
    days_ahead = (date - today_state).days
    cost = 0 if days_ahead <= 1 else min(days_ahead - 1, 5)  # Cap cost at 5 bucks

    # Check if the slot is already booked
    if Event.query.filter_by(date=date, start_hour=hour, major_city=state, suburb=suburb).first():
        return jsonify({"success": False, "message": "Slot already booked in this state and suburb."}), 400

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
        major_city=state,  # Store state in major_city
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

@main.route('/all-events', methods=['GET'])
def all_events():
    """Display all events in the database."""
    # Query all events
    events = Event.query.all()

    # If the client requests JSON format (optional)
    if request.args.get('format') == 'json':
        events_data = [
            {
                "id": event.id,
                "user_id": event.user_id,
                "major_city": event.major_city,
                "suburb": event.suburb,
                "event_type": event.event_type,
                "date": event.date.strftime('%Y-%m-%d'),
                "start_hour": event.start_hour,
                "latitude": event.latitude,
                "longitude": event.longitude,
                "radius": event.radius
            }
            for event in events
        ]
        return jsonify(events_data)

    # Render HTML template
    return render_template('all_events.html', events=events)
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

@main.route('/suburbs/<state>', methods=['GET'])
def get_suburbs(state):
    """Fetch suburbs for a selected state."""
    try:
        suburbs = fetch_suburbs_by_state(state)  # Replace with your API call or static list
        return jsonify(suburbs)  # Return suburbs as JSON
    except Exception as e:
        print(f"Error fetching suburbs for state {state}: {e}")
        return jsonify([]), 500



# Link Strava account route
@main.route('/link-strava')
def link_strava():
    """Start the Strava OAuth flow for the logged-in user."""
    if 'user_id' not in session:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('main.login'))

    # Dynamically fetch client_id from configuration
    client_id = current_app.config.get('STRAVA_CLIENT_ID')
    print(f"Client ID is {client_id}")
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
    print(f"Code is {code}")
    
    if not code:
        flash('Authorization failed. Please try again.', 'danger')
        return redirect(url_for('main.account'))

    client_id = current_app.config.get('STRAVA_CLIENT_ID')
    client_secret = current_app.config.get('STRAVA_CLIENT_SECRET')
    token_url = current_app.config.get('STRAVA_TOKEN_URL')
    print(f"Client ID is {client_id}")
    print(f"Client Secret is {client_secret}") 
    print(f"Token url is {token_url}")

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
