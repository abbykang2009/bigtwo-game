import os
import random
import uuid
from flask import Flask, request, jsonify, session, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'bigtwo_game_key_' + str(random.randint(1000, 9999))  # Random secret key

# Initialize Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*")

# Game data storage
games = {}
active_rooms = {}

@app.route('/')
def home():
    return render_template('index.html')

# API Endpoints
@app.route('/create_game', methods=['POST'])
def create_game():
    player_name = request.json.get('player_name')
    room_id = 'room_' + str(uuid.uuid4())[:6]
    
    games[room_id] = {
        'players': {player_name: {'ready': False}},
        'status': 'waiting'
    }
    
    return jsonify({
        'room_id': room_id,
        'player_name': player_name
    })

@app.route('/join_game', methods=['POST'])
def join_game():
    room_id = request.json.get('room_id')
    player_name = request.json.get('player_name')
    
    if room_id not in games:
        return jsonify({'error': 'Room not found'}), 404
        
    games[room_id]['players'][player_name] = {'ready': False}
    return jsonify({'status': 'joined'})

# Socket.IO Events
@socketio.on('create_room')
def handle_create_room(data):
    room_id = data['room_id']
    username = data['username']
    active_rooms[room_id] = [username]
    join_room(room_id)
    emit('room_update', {'players': active_rooms[room_id]}, to=room_id)

@socketio.on('join_room')
def handle_join_room(data):
    room_id = data['room_id']
    username = data['username']
    
    if room_id in active_rooms:
        active_rooms[room_id].append(username)
        join_room(room_id)
        emit('room_update', {'players': active_rooms[room_id]}, to=room_id)
    else:
        emit('error', {'message': 'Room does not exist'})

@socketio.on('connect')
def handle_connect():
    print("A user connected")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
