import os
import random
import uuid
from collections import defaultdict
from flask import Flask, request, jsonify, session, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'bigtwo_key_' + str(random.randint(1000, 9999))

# Initialize Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*")

# Game data storage
games = {}
active_rooms = {}

class BigTwoGame:
    def __init__(self, room_id):
        self.room_id = room_id
        self.players = {}  # {player_name: {'hand': [], 'passed': False}}
        self.draw_pile = []
        self.face_up_card = None
        self.current_player = None
        self.initialize_deck()
    
    def initialize_deck(self):
        suits = ['spades', 'hearts', 'diamonds', 'clubs']
        ranks = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2']
        self.deck = [(rank, suit) for suit in suits for rank in ranks]
        random.shuffle(self.deck)
    
    def add_player(self, player_name):
        if len(self.players) >= 3:
            return False
        self.players[player_name] = {'hand': [], 'passed': False}
        return True
    
    def deal_cards(self):
    num_players = len(self.players)
    if num_players not in [2, 3]:
        return False
    
    # Reset deck and shuffle
    self.initialize_deck()
    
    # Deal face up card (last card in deck)
    self.face_up_card = self.deck.pop()
    
    # Deal to players
    if num_players == 2:
        # Deal 17 cards to each player (alternating)
        for i in range(17):
            self.players[list(self.players.keys())[0]]['hand'].append(self.deck.pop())
            self.players[list(self.players.keys())[1]]['hand'].append(self.deck.pop())
        self.draw_pile = self.deck.copy()  # Remaining 17 cards
    else:  # 3 players
        for i in range(17):
            self.players[list(self.players.keys())[0]]['hand'].append(self.deck.pop())
            self.players[list(self.players.keys())[1]]['hand'].append(self.deck.pop())
            self.players[list(self.players.keys())[2]]['hand'].append(self.deck.pop())
        self.draw_pile = []
    
    # Assign face up card
    self.assign_face_up_card()
    return True
    
    def assign_face_up_card(self):
        target_rank, target_suit = ('3', 'diamonds')
        if self.face_up_card == ('3', 'diamonds'):
            target_rank, target_suit = ('3', 'clubs')
        
        for player_name, data in self.players.items():
            if (target_rank, target_suit) in data['hand']:
                data['hand'].append(self.face_up_card)
                self.face_up_card_owner = player_name
                return
        
        # If no player has the target card, assign to random player
        random_player = random.choice(list(self.players.keys()))
        self.players[random_player]['hand'].append(self.face_up_card)
        self.face_up_card_owner = random_player

@app.route('/')
def home():
    return render_template('index.html')

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

@socketio.on('player_ready')
def handle_player_ready(data):
    room_id = data['room_id']
    player_name = data['player_name']
    
    if room_id not in games:
        return
    
    if 'game' not in games[room_id]:
        games[room_id]['game'] = BigTwoGame(room_id)
    
    games[room_id]['players'][player_name]['ready'] = True
    games[room_id]['game'].add_player(player_name)
    
    all_ready = all(p['ready'] for p in games[room_id]['players'].values())
    min_players = 2
    
    if all_ready and len(games[room_id]['players']) >= min_players:
        if games[room_id]['game'].deal_cards():
            # First show face up card to all players
            emit('show_face_up_card', {
                'card': games[room_id]['game'].face_up_card,
                'owner': games[room_id]['game'].face_up_card_owner
            }, room=room_id)
            
            # Then deal hands
            for player, data in games[room_id]['game'].players.items():
                emit('deal_cards', {
                    'hand': data['hand'],
                    'draw_pile_count': len(games[room_id]['game'].draw_pile),
                    'room_id': room_id
                }, room=player)
            
            emit('start_game', {
                'room_id': room_id,
                'message': 'Game started!'
            }, room=room_id)
    else:
        emit('waiting_status', {
            'ready_players': sum(1 for p in games[room_id]['players'].values() if p['ready']),
            'total_players': len(games[room_id]['players'])
        }, room=room_id)

@socketio.on('connect')
def handle_connect():
    print("A user connected")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
