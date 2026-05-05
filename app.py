from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_login import UserMixin, LoginManager, login_user, logout_user
from dotenv import load_dotenv
from flask_jwt_extended import set_access_cookies, create_access_token, JWTManager, jwt_required, get_jwt_identity, unset_jwt_cookies

import os
import math
from datetime import timedelta 

app = Flask(__name__)
bcrypt = Bcrypt(app)

load_dotenv()

#keeping values hidden, will help when we transition to web
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_EXPIRATION_DELTA'] = timedelta(days=7)

#!!! set True in production !!!
app.config['JWT_COOKIE_SECURE'] = False

#TODO: figureout how to use CSRF when sending player guess, weird cookie thing.
app.config['JWT_COOKIE_CSRF_PROTECT'] = False 

jwt = JWTManager(app)
db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True)
    password = db.Column(db.String, nullable=False)
    
    
login_manager = LoginManager(app)
login_manager.login_view = 'login'

#Function used to calculate distance between the guess and target.
def calcDistance(lat1, lat2, lng1, lng2):
    earth_radius = 3959 #miles
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)
    lng1 = math.radians(lng1)
    lng2 = math.radians(lng2)
    
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    hav = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
    
    theta = 2*math.asin(math.sqrt(hav))
    distance = earth_radius*theta
    
    #returns float
    return distance

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    #Checks to see if user has already loggin in.
    
    #If submit button is pressed, continue to verification
    if request.method == 'POST':
        #Grabs username and password from input fields
        username = request.form.get('username')
        password = request.form.get('password')
        
        #Verification of login credentials
        user = User.query.filter_by(username=username).first()
        if not user or not bcrypt.check_password_hash(user.password, password):
            flash("Invalid username or password.", "danger")
            return redirect(url_for('login'))
        
        #If verificaton passes, login user
        login_user(user)
        
        access_token = create_access_token(identity=username)
        response = redirect(url_for('main'))
        
        set_access_cookies(response, access_token)
        
        return response
        
    #Renders the initial page    
    return render_template('login.html')

#Routes to main page
@app.route('/main')
@jwt_required()
def main():
    current_user = get_jwt_identity()
    return render_template('main.html', username=current_user)

#Registers User with hash encryption
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        #Data validation check
        if not username or not password:
            flash("All fields are required", "danger")
            return render_template("register.html")
        
        #creates encrypted password
        hashed_pass = bcrypt.generate_password_hash(password).decode("utf-8")
        
        new_user = User(
            username=username,
            password = hashed_pass
        )
        
        #Adds username and hashed password to db
        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Registration Complete", "success")
            return redirect('login')
        except IntegrityError:
            db.session.rollback()
            flash("That username is already taken. Try another.", "warning")
            
            
    return render_template('register.html')

#serverside guess processing
@app.route('/guess', methods=['POST'])
@jwt_required()
def process_guess():
    data = request.get_json()
        
    response_lat = data['lat']
    response_lang = data['lang']
    
    #test data: CTK Quad 
    #Should grab lat and lang from database when we have it ready
    
    target_lat = 37.36620076648134
    target_lang = -120.42320671417902
    
    distance = calcDistance(response_lat, target_lat, response_lang, target_lang) * 5280 #Feet
    
    #Used to debug, will remove later
    print(f"feet away: {round(distance, 1)}")
    
    #Sends the distance from the target and coordinates back to browser
    return jsonify({
        'distance': round(distance, 2),
        "target": {"lat": target_lat, "lng": target_lang}
    })

        
@app.route('/logout')
def logout():
    logout_user()
    response = redirect(url_for('login'))
    unset_jwt_cookies(response)
    flash("Logged out", "info")
    return response

#Runs once JWT token expires
@jwt.expired_token_loader
def expired_token(jwt_header, jwt_payload):
    response = redirect(url_for('login'))
    
    unset_jwt_cookies(response)
    
    return response

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)