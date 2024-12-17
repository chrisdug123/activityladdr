from . import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from pytz import timezone 

BRISBANE_TZ = timezone('Australia/Brisbane')
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)  # New field
    
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    strava_id = db.Column(db.String(50), nullable=True)  # Stores Strava user ID
    strava_access_token = db.Column(db.String(255), nullable=True)
    strava_refresh_token = db.Column(db.String(255))
    strava_expires_at = db.Column(db.Integer)    # Stores Strava access token
    bucks = db.Column(db.Integer, default=5)  # Weekly Bucks balance
    last_bucks_update = db.Column(db.DateTime, default=datetime.utcnow)
    private_event_ends = db.Column(db.DateTime, nullable=True)  # End time for private event
    last_activated = db.Column(db.DateTime, nullable=True)  # Last activation time for weekly cooldown
    linked_accounts = db.Column(db.Boolean, default=False)  # Example field for linked accounts
    overall_points = db.Column(db.Integer, default=0)
    # Caching fields for activity data
    monthly_data = db.Column(db.JSON, default={
        'run': {'distance': 0, 'pace': 0, 'points': 0, 'avg_multiplier': 1},
        'ride': {'distance': 0, 'pace': 0, 'points': 0, 'avg_multiplier': 1},
    }) # Cached monthly totals
    yearly_data = db.Column(db.JSON, nullable=True)   # Cached yearly totals
    monthly_last_updated = db.Column(db.DateTime, nullable=True)  # Last updated timestamp for monthly data
    yearly_last_updated = db.Column(db.DateTime, nullable=True)   # Last updated timestamp for yearly data

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def regenerate_bucks(self):
        """Regenerates bucks if a week has passed since the last update."""
        if not self.last_bucks_update or (datetime.utcnow() - self.last_bucks_update) >= timedelta(weeks=1):
            self.bucks = 5  # Reset to 5 bucks
            self.last_bucks_update = datetime.utcnow()

    def can_activate(self):
        """Check if the user can activate a private event (Brisbane-based)."""
        if self.last_activated:
            # Convert `last_activated` to Brisbane timezone
            last_activated_brisbane = (
                BRISBANE_TZ.localize(self.last_activated) if self.last_activated.tzinfo is None
                else self.last_activated.astimezone(BRISBANE_TZ)
            )

            # Calculate the next activation time
            next_activation = last_activated_brisbane + timedelta(days=7)

            # Get the current time in Brisbane timezone
            now_brisbane = datetime.now(BRISBANE_TZ)

            # Compare the times
            return now_brisbane >= next_activation

        # If no activation has occurred yet, activation is allowed
        return True # If no prior activation, activation is allowed
    def private_event_active(self):
        """Check if a private event is active (Brisbane-based)."""
        if self.private_event_ends:
            private_event_ends_brisbane = BRISBANE_TZ.localize(self.private_event_ends)
            now_brisbane = datetime.now(BRISBANE_TZ)
            return now_brisbane < private_event_ends_brisbane
        return False
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Nullable for community events
    user = db.relationship('User', backref='events')
    major_city = db.Column(db.String(100), nullable=False)
    suburb = db.Column(db.String(100), nullable=False)
    event_type = db.Column(db.String(20), nullable=False, default='public')  # Default to public
    date = db.Column(db.Date, nullable=False)
    start_hour = db.Column(db.Integer, nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    radius = db.Column(db.Float, default=1.0)

     
    def get_multiplier(self, user):
        """Determine the multiplier for an event."""
        if self.event_type == 'public':  # Public events always have a 10x multiplier
            return 10
        if user.private_event_active():  # Private event active for the user
            return 3
        return 1  # Default multiplier for other events

    @property
    def cost(self):
        """Return cost in bucks based on event type."""
        return 5 if self.event_type == 'community' else 3

    @property
    def end_hour(self):
        """Calculate the end hour of the 3-hour time slot."""
        return (self.start_hour + 3) % 24  # Wrap around for midnight slots
