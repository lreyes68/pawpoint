from flask import Flask, render_template, request, redirect, url_for, flash
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required
from dotenv import load_dotenv

import os

app = Flask(__name__)
bcrypt = Bcrypt(app)

load_dotenv()

#keeping values hidden, will help when we transition to web
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True)
    password = db.Column(db.String, nullable=False)
    
    
login_manager = LoginManager(app)
login_manager.login_view = 'login'

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
        
        return redirect(url_for('main'))
        
    #Renders the initial page    
    return render_template('login.html')

#Routes to main page
@app.route('/main')
def main():
    return render_template('main.html')

#Registers User with hash encryption
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        #Data validation check
        if not username or not password:
            flash("All fields are requires", "danger")
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
        
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)