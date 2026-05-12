from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_login import UserMixin, LoginManager, login_user, logout_user
from dotenv import load_dotenv
from flask_jwt_extended import set_access_cookies, create_access_token, JWTManager, jwt_required, get_jwt_identity, unset_jwt_cookies

import os
import math
import random
import re
from datetime import datetime, timedelta, timezone
app = Flask(__name__)
bcrypt = Bcrypt(app)

basedir = os.path.abspath(os.path.dirname(__file__))

#keeping values hidden, will help when we transition to web
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')  or 'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)
#!!! set True in production !!!
app.config['JWT_COOKIE_SECURE'] = True


jwt = JWTManager(app)
db = SQLAlchemy(app)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ROUND_DURATION  = 60   # seconds players have to guess
BETWEEN_ROUNDS  = 10   # seconds to show results before next round starts
STARTING_HP     = 6000
BASE_DAMAGE     = 500  # HP lost per damage multiplier level
INTERMISSION    = 10        # seconds between rounds
LOBBY_WAIT_TIME = 10   #seconds until start of round when 2 players join

# Campus locations pool  {name, photo filename, lat, lng}
LOCATIONS = [
    {"name": "Photo 1",         "photo": "photos/12xz0210z.jpeg", "lat": 37.36261,  "lng": -120.42525},
    {"name": "Photo 2",       "photo": "photos/AIzjioAIOAnx102.jpeg", "lat": 37.36289,  "lng": -120.42691},
    {"name": "Photo 3",       "photo": "photos/asdasoaxoaskx.jpeg", "lat": 37.36493,  "lng": -120.42778},
    {"name": "Photo 4",       "photo": "photos/aslkdmasdasd.jpeg", "lat": 37.36420,  "lng": -120.42727},
    {"name": "Photo 5",       "photo": "photos/pvoigpovmpov.jpeg", "lat": 37.36384,  "lng": -120.42967},
    
    # Add more locations here as you photograph them
]

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(25), unique=True)
    password     = db.Column(db.String, nullable=False)
    best_streak  = db.Column(db.Integer, default=0)
    total_wins   = db.Column(db.Integer, default=0)


# Represents one round in the infinite public lobby
class Round(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    location   = db.Column(db.String, nullable=False)   # JSON-encoded location dict
    started_at = db.Column(db.DateTime, nullable=True)  # None = waiting for players
    ends_at    = db.Column(db.DateTime, nullable=True)
    wait_ends_at = db.Column(db.DateTime, nullable=True)
    finished   = db.Column(db.Boolean, default=False)
    winner     = db.Column(db.String, nullable=True)


# A player's slot in a round
class RoundPlayer(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    round_id     = db.Column(db.Integer, db.ForeignKey('round.id'), nullable=False)
    username     = db.Column(db.String, nullable=False)
    hp           = db.Column(db.Integer, default=STARTING_HP)
    current_streak = db.Column(db.Integer, default=0)
    guess_lat    = db.Column(db.Float, nullable=True)
    guess_lng    = db.Column(db.Float, nullable=True)
    distance_ft  = db.Column(db.Float, nullable=True)   # filled after round ends
    damage_taken = db.Column(db.Integer, nullable=True)
    eliminated   = db.Column(db.Boolean, default=False)


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
    hav = min(1.0, max(0.0, hav))   # clamp to avoid floating-point ValueError

    theta = 2*math.asin(math.sqrt(hav))
    distance = earth_radius*theta

    #returns float
    return distance


def damage_multiplier(diff_ft):
    """Return a damage multiplier based on how many feet farther a player was
    compared to the best guesser of the round."""
    if diff_ft <= 0:
        return 0
    elif diff_ft <= 100:
        return 2
    elif diff_ft <= 300:
        return 3
    elif diff_ft <= 600:
        return 4
    elif diff_ft <= 1200:
        return 5
    else:
        return 6


def get_or_create_current_round():
    """Return the active (non-finished) round, creating one if needed."""
    import json
    current = Round.query.filter_by(finished=False).order_by(Round.id.desc()).first()
    if current is None:
        loc = random.choice(LOCATIONS)
        current = Round(location=json.dumps(loc), finished=False)
        db.session.add(current)
        db.session.commit()
    return current


def active_player_count(round_id):
    return RoundPlayer.query.filter_by(round_id=round_id, eliminated=False).count()


def finish_round(round_obj):
    """Score the round: apply damage, update streaks, then open a new round."""
    import json
    players = RoundPlayer.query.filter_by(round_id=round_obj.id, eliminated=False).all()

    guessed = [p for p in players if p.distance_ft is not None]

    if guessed:
        best_dist = min(p.distance_ft for p in guessed)
        for p in guessed:
            diff = p.distance_ft - best_dist
            mult = damage_multiplier(diff)
            dmg = BASE_DAMAGE * mult
            p.damage_taken = dmg
            p.hp -= dmg
            if p.hp <= 0:
                p.hp = 0
                p.eliminated = True
            else:
                p.current_streak += 1
            # Always record best streak whether the player survives or is eliminated
            user = User.query.filter_by(username=p.username).first()
            if user and p.current_streak > user.best_streak:
                user.best_streak = p.current_streak

    # Players who never guessed take max damage
    for p in players:
        if p.distance_ft is None:
            p.damage_taken = BASE_DAMAGE * 6
            p.hp = max(0, p.hp - p.damage_taken)
            if p.hp <= 0:
                p.eliminated = True
            user = User.query.filter_by(username=p.username).first()
            if user and p.current_streak > user.best_streak:
                user.best_streak = p.current_streak

    round_obj.finished = True

    # Create next round immediately so survivors carry over
    # loc = random.choice(LOCATIONS)
    # new_round = Round(location=json.dumps(loc), finished=False)
    # db.session.add(new_round)
    # db.session.flush()  # get new_round.id

    # Carry surviving players into the new round
    survivors = RoundPlayer.query.filter_by(round_id=round_obj.id, eliminated=False).all()
    
    if len(survivors) > 1:
        loc = random.choice(LOCATIONS)
        new_round = Round(location=json.dumps(loc), finished=False)
        
        now = datetime.now(timezone.utc)
        new_round.started_at = now
        new_round.ends_at = now + timedelta(seconds=ROUND_DURATION)
        
        db.session.add(new_round)
        db.session.flush()  # get new_round.id
        
        for p in survivors:
            carry = RoundPlayer(
                round_id=new_round.id,
                username=p.username,
                hp=p.hp,
                current_streak=p.current_streak
            )
            db.session.add(carry)
        db.session.commit()
        return new_round
    else:
        if len(survivors) == 1:
            winner_name = survivors[0].username
            round_obj.winner = winner_name
            
            winner_user = User.query.filter_by(username=winner_name).first()
            if winner_user:
                winner_user.total_wins += 1
        else:
            round_obj.winner = "Draw"
        db.session.commit()
        return round_obj
 
def is_match_in_progress(round_id):
    ongoing = RoundPlayer.query.filter(
        RoundPlayer.round_id == round_id,
        RoundPlayer.current_streak > 0
    ).first()
    return ongoing is not None
     
 
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
 
#Routes to hub page
@app.route('/main')
@jwt_required()
def main():
    current_user = get_jwt_identity()
    return render_template('main.html', username=current_user)
 
#Routes to game page
@app.route('/game')
@jwt_required()
def game():
    current_user = get_jwt_identity()
    return render_template('game.html', username=current_user)
 
#Routes to leaderboard
@app.route('/leaderboard')
@jwt_required()
def leaderboard():
    scores = (User.query
              .filter(User.total_wins > 0)
              .order_by(User.total_wins.desc())
              .limit(50)
              .all())
    return render_template('leaderboard.html', scores=scores)
 
#Routes to staff page
@app.route('/staff')
@jwt_required()
def staff():
    return render_template('staff.html')
 
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
        
        if len(username) > 25:
            flash("Username must be 25 characters or less.", "warning")
            
        if len(username) < 3:
            flash("Username must be at least 3 characters", "warning")
        
        if not re.match(r"^[a-zA-Z0-9_]+$", username):
            flash("Username can only contain letters, numbers, and underscores.", "danger")
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
 
#serverside guess processing (legacy single-player, kept for reference)
@app.route('/guess', methods=['POST'])
@jwt_required()
def process_guess():
    data = request.get_json()
    response_lat = data['lat']
    response_lang = data['lang']
    target_lat  = 37.36620076648134
    target_lang = -120.42320671417902
    distance = calcDistance(response_lat, target_lat, response_lang, target_lang) * 5280
    return jsonify({'distance': round(distance, 2), "target": {"lat": target_lat, "lng": target_lang}})


# Lobby / Multiplayer routes
@app.route('/lobby/join', methods=['POST'])
@jwt_required()
def lobby_join():
    """Join the public lobby. Returns the current round state."""
    import json
    username = get_jwt_identity()
    round_obj = get_or_create_current_round()

    if round_obj.started_at or is_match_in_progress(round_obj.id):
        return jsonify({'status': 'waiting', 'message': 'Match in progress. Wait for a winner.'})
    
    # Check if player is already in this round
    existing = RoundPlayer.query.filter_by(round_id=round_obj.id, username=username).first()

    if existing:
        # Player left and wants to rejoin — if the round is still waiting, let them back in
        if existing.eliminated:
            existing.eliminated  = False
            existing.guess_lat   = None
            existing.guess_lng   = None
            existing.distance_ft = None
            existing.damage_taken = None
            db.session.commit()
        # If the round is already running they have to wait; leave the eliminated flag in place
    else:
        # If the round is already running, player must wait for the next one
        new_player = RoundPlayer(
            round_id=round_obj.id,
            username=username,
            hp=STARTING_HP,
            current_streak=0
        )
        db.session.add(new_player)
        db.session.commit()


    # Start the round if there are now >= 2 active non-eliminated players and it hasn't started yet
    player_count = active_player_count(round_obj.id)
    if not round_obj.started_at and not round_obj.wait_ends_at and player_count >= 2:
        now = datetime.now(timezone.utc)
        round_obj.wait_ends_at = now + timedelta(seconds=LOBBY_WAIT_TIME)
        
        db.session.commit()

    loc = json.loads(round_obj.location)
    return jsonify(_round_state(round_obj, username))


@app.route('/lobby/state', methods=['GET'])
@jwt_required()
def lobby_state():
    """Poll this every few seconds to get the current round state."""
    import json
    username  = get_jwt_identity()
    round_obj = get_or_create_current_round()

    now = datetime.now(timezone.utc)

    # Auto-finish round if time has expired
    if round_obj.started_at and round_obj.ends_at and not round_obj.finished:
        ends_at_aware = round_obj.ends_at.replace(tzinfo=timezone.utc)
        if now >= ends_at_aware:
            round_obj = finish_round(round_obj)

    if round_obj.started_at and not round_obj.finished:
        count = active_player_count(round_obj.id)
        if count < 2:
            if count == 1:
                survivor = RoundPlayer.query.filter_by(round_id=round_obj.id, eliminated=False).first()
                if survivor:
                    round_obj.winner = survivor.username
                    winner_user = User.query.filter_by(username=survivor.username).first()
                    if winner_user:
                        winner_user.total_wins += 1
            else:
                round_obj.winner = "Draw"
            round_obj.ends_at = now
            round_obj.finished = True
            db.session.commit()

    # Between-rounds window: keep showing the finished round (with results & flag) for
    # BETWEEN_ROUNDS seconds so players can see where the location was before the next round.
    last_finished = Round.query.filter_by(finished=True).order_by(Round.id.desc()).first()
    if last_finished and last_finished.ends_at:
        ends_at_aware = last_finished.ends_at.replace(tzinfo=timezone.utc)
        gap = (now - ends_at_aware).total_seconds()
        if 0 <= gap < BETWEEN_ROUNDS:
            # Pre-register any observer (player not yet in the new round) during the
            # interlude so they don't miss the join window due to the auto-start race.
            next_round = get_or_create_current_round()
            
            #Oberserver may not join until it is the start of a new game.
            if not next_round.started_at and not is_match_in_progress(next_round.id):
                obs_existing = RoundPlayer.query.filter_by(
                    round_id=next_round.id, username=username).first()
                if not obs_existing:
                    obs_player = RoundPlayer(
                        round_id=next_round.id,
                        username=username,
                        hp=STARTING_HP,
                        current_streak=0
                    )
                    db.session.add(obs_player)
                    db.session.commit()

            state = _round_state(last_finished, username)
            state['next_round_in'] = max(0, int(BETWEEN_ROUNDS - gap))
            return jsonify(state)

    # If we just finished the round but the window has already passed, refresh to the new round
    if round_obj.finished:
        round_obj = get_or_create_current_round()
    
    if round_obj.wait_ends_at and not round_obj.finished and not round_obj.started_at:
        wait_ends_aware = round_obj.wait_ends_at.replace(tzinfo=timezone.utc)
        if now >= wait_ends_aware:
            round_obj.started_at = now
            round_obj.ends_at = now + timedelta(seconds=ROUND_DURATION)
            round_obj.wait_ends_at = None
            db.session.commit()
    if not round_obj.started_at and round_obj.wait_ends_at:
        if active_player_count(round_obj.id) < 2:
            round_obj.wait_ends_at = None
            db.session.commit()
    
    if not round_obj.started_at and not round_obj.finished and not round_obj.wait_ends_at:
        if active_player_count(round_obj.id) >= 2:
            round_obj.wait_ends_at = now + timedelta(seconds=LOBBY_WAIT_TIME)
            db.session.commit()
    # Add observer to the new round BEFORE auto-starting, so they count toward the player total
    # and don't get locked out because started_at gets set first.
    # Also re-activate players whose eliminated flag was set by sendBeacon/refresh
    # in an unstarted round so they aren't permanently locked out.
    if not round_obj.started_at and not round_obj.finished:
        if is_match_in_progress(round_obj.id):
            return jsonify(_round_state(round_obj, username))
        existing = RoundPlayer.query.filter_by(round_id=round_obj.id, username=username).first()
        if not existing:
            new_player = RoundPlayer(
                round_id=round_obj.id,
                username=username,
                hp=STARTING_HP,
                current_streak=0
            )
            db.session.add(new_player)
            db.session.commit()
        elif existing.eliminated:
            # Round hasn't started yet — let the player back in with reset stats
            existing.eliminated  = False
            existing.guess_lat   = None
            existing.guess_lng   = None
            existing.distance_ft = None
            existing.damage_taken = None
            db.session.commit()

    # Auto-start a waiting round once 2+ active players are present

    return jsonify(_round_state(round_obj, username))


@app.route('/lobby/guess', methods=['POST'])
@jwt_required()
def lobby_guess():
    """Submit a guess for the current multiplayer round."""
    import json
    username = get_jwt_identity()
    data     = request.get_json()
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    round_obj = Round.query.filter_by(finished=False).order_by(Round.id.desc()).first()
    if not round_obj or not round_obj.started_at:
        return jsonify({'error': 'No active round'}), 400

    now = datetime.now(timezone.utc)
    ends_at_aware = round_obj.ends_at.replace(tzinfo=timezone.utc)
    if now > ends_at_aware:
        return jsonify({'error': 'Round already ended'}), 400

    player = RoundPlayer.query.filter_by(round_id=round_obj.id, username=username).first()
    if not player:
        return jsonify({'error': 'You are not in this round'}), 400
    if player.guess_lat is not None:
        return jsonify({'error': 'Already submitted a guess this round'}), 400

    loc = json.loads(round_obj.location)
    dist_ft = calcDistance(data['lat'], loc['lat'], data['lng'], loc['lng']) * 5280

    player.guess_lat   = data['lat']
    player.guess_lng   = data['lng']
    player.distance_ft = round(dist_ft, 2)
    
    active_players = RoundPlayer.query.filter_by(round_id=round_obj.id, eliminated=False).all()
    if active_players and all(p.distance_ft is not None for p in active_players):
        
        new_end = now_utc_naive + timedelta(seconds=7)
        if round_obj.ends_at > new_end:
            round_obj.ends_at = new_end
    
    db.session.commit()

    return jsonify({'distance_ft': player.distance_ft})


def _round_state(round_obj, username):
    """Build the JSON payload describing the current round to send to the client."""
    import json
    now = datetime.now(timezone.utc)
    loc = json.loads(round_obj.location)

    player = RoundPlayer.query.filter_by(round_id=round_obj.id, username=username).first()
    player_count = active_player_count(round_obj.id)

    seconds_left = 0
    if round_obj.started_at and round_obj.ends_at:
        ends_at_aware = round_obj.ends_at.replace(tzinfo=timezone.utc)
        seconds_left = max(0, int((ends_at_aware - now).total_seconds()))
    lobby_wait_seconds = 0
    if round_obj.wait_ends_at:
        wait_ends_aware = round_obj.wait_ends_at.replace(tzinfo=timezone.utc)
        lobby_wait_seconds = max (0, int((wait_ends_aware - now).total_seconds()))
        
    state = {
        'round_id':     round_obj.id,
        'finished':     round_obj.finished,
        'winner':       round_obj.winner,
        'player_count': player_count,
        'seconds_left': seconds_left,
        'lobby_wait_seconds': lobby_wait_seconds,
        'waiting':      player_count < 2 and not round_obj.started_at,
        'location': {
            'photo':  loc['photo'],
            'name':   loc['name'],
            'lat':    loc['lat'] if round_obj.finished else None,  # reveal after round
            'lng':    loc['lng'] if round_obj.finished else None,
        },
        'me': None
    }

    if player:
        state['me'] = {
            'username':      player.username,
            'hp':            player.hp,
            'current_streak': player.current_streak,
            'eliminated':    player.eliminated,
            'guessed':       player.guess_lat is not None,
            'damage_taken':  player.damage_taken,
            'distance_ft':   player.distance_ft,         
        }

    if round_obj.finished:
        # Send full results so the client can show the scoreboard
        all_players = (RoundPlayer.query
                       .filter_by(round_id=round_obj.id)
                       .order_by(RoundPlayer.distance_ft.asc().nullslast())
                       .all())
        state['results'] = [
            {
                'username':    p.username,
                'distance_ft': p.distance_ft,
                'damage_taken': p.damage_taken,
                'hp':          p.hp,
                'eliminated':  p.eliminated,
            }
            for p in all_players
        ]

    return state


@app.route('/lobby/leave', methods=['POST'])
@jwt_required(optional=True)
def lobby_leave():
    """Remove the calling player from the current active round."""
    username  = get_jwt_identity()
    if not username:
        return jsonify({'ok': True})  # unauthenticated (e.g. sendBeacon after logout)
    round_obj = Round.query.filter_by(finished=False).order_by(Round.id.desc()).first()
    if round_obj:
        player = RoundPlayer.query.filter_by(round_id=round_obj.id, username=username).first()
        if player and not player.eliminated:
            player.eliminated     = True
            player.hp             = STARTING_HP
            player.current_streak = 0
            db.session.commit()
    return jsonify({'ok': True})


@app.route('/logout')
def logout():
    # Remove player from active lobby if they were in one
    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity as _get_identity
        verify_jwt_in_request(locations=['cookies'], optional=True)
        username = _get_identity()
        if username:
            round_obj = Round.query.filter_by(finished=False).order_by(Round.id.desc()).first()
            if round_obj:
                player = RoundPlayer.query.filter_by(round_id=round_obj.id, username=username).first()
                if player and not player.eliminated:
                    player.eliminated = True
                    db.session.commit()
    except Exception:
        pass
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
    app.run(host='0.0.0.0', debug=True, port=5001)
