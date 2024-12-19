import os

class Config:
    SECRET_KEY = 'your_secret_key_here'

    #below is dev db
    SQLALCHEMY_DATABASE_URI = 'sqlite:///activityladdr2.db'
    #SQLALCHEMY_DATABASE_URI = 'sqlite:////home/site/wwwroot/ActivityLaddr/instance/activityladdr2.db'



    #below is prod db
    #SQLALCHEMY_DATABASE_URI = 'sqlite:///activityladdr.db'
    #SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Strava API Credentials
    STRAVA_CLIENT_ID = '107088'  # Replace with your individual Client ID
    STRAVA_CLIENT_SECRET = '5bcbe946accb34f85158578824e42f7e7bb162d3'  # Replace with your individual Client Secret
    STRAVA_AUTH_URL = 'https://www.strava.com/oauth/authorize'
    STRAVA_TOKEN_URL = 'https://www.strava.com/oauth/token'
