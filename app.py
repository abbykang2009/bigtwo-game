from flask import Flask, render_template, request, jsonify, session
import random
from collections import defaultdict
from flask_socketio import SocketIO, emit, join_room, leave_room
from waitress import serve

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # <-- ADD THIS LINE (temporary for testing)

@app.route("/")
def home():
    return "Hello World"

# ADD THESE LINES FOR ROOM MANAGEMENT
# Add below your existing socketio code
active_rooms = {}  # Tracks all rooms and players

@socketio.on('create_room')
def handle_create_room(data):
    room_id = data['room_id']
    username = data['username']
    active_rooms[room_id] = [username]  # New room with creator
    join_room(room_id)
    emit('room_update', {'players': active_rooms[room_id]}, to=room_id)

@socketio.on('join_room')
def handle_join_room(data):
    room_id = data['room_id']
    username = data['username']
    
    if room_id in active_rooms:
        active_rooms[room_id].append(username)  # Add player
        join_room(room_id)
        emit('room_update', {'players': active_rooms[room_id]}, to=room_id)
    else:
        emit('error', {'message': 'Room does not exist'})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # ← Use Render's PORT or default
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)

games = {}

class BigTwoGame:
    def __init__(self, room_id):
        self.room_id = room_id
        self.players = {}
        self.deck = []
        self.piles = [[], [], []]
        self.face_up_card = None
        self.current_player = None
        self.last_played = None
        self.game_started = False
        self.scores = {}
        self.winner = None
        self.min_players = 2
        self.initialize_deck()
        
    def initialize_deck(self):
        suits = ['spades', 'hearts', 'diamonds', 'clubs']
        ranks = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2']
        self.deck = [(rank, suit) for suit in suits for rank in ranks]
        random.shuffle(self.deck)
        
        self.piles[0] = self.deck[:17]
        self.piles[1] = self.deck[17:34]
        self.piles[2] = self.deck[34:51]
        self.face_up_card = self.deck[51]
        
    def add_player(self, player_id, player_name):
        if len(self.players) >= 3:
            return False
            
        self.players[player_id] = {
            'name': player_name,
            'hand': [],
            'ready': False,
            'score': 0
        }
        return True
        
    def start_game(self):
        if len(self.players) < self.min_players or not all(p['ready'] for p in self.players.values()):
            return False
            
        for i, player_id in enumerate(self.players.keys()):
            self.players[player_id]['hand'] = self.piles[i]
                
        self.determine_starting_player()
        self.game_started = True
        return True
        
    def determine_starting_player(self):
        target_rank, target_suit = ('3', 'diamonds')
        if self.face_up_card == ('3', 'diamonds'):
            target_rank, target_suit = ('3', 'clubs')
        
        starting_player = None
        
        for player_id, data in self.players.items():
            if (target_rank, target_suit) in data['hand']:
                starting_player = player_id
                break
                
        if starting_player is None:
            suit_order = {'diamonds': 0, 'clubs': 1, 'hearts': 2, 'spades': 3}
            rank_order = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2']
            smallest_card = None
            
            for player_id, data in self.players.items():
                for card in data['hand']:
                    rank, suit = card
                    if smallest_card is None:
                        smallest_card = card
                        starting_player = player_id
                    else:
                        if rank_order.index(rank) < rank_order.index(smallest_card[0]):
                            smallest_card = card
                            starting_player = player_id
                        elif rank == smallest_card[0]:
                            if suit_order[suit] < suit_order[smallest_card[1]]:
                                smallest_card = card
                                starting_player = player_id
        
        if starting_player:
            self.players[starting_player]['hand'].append(self.face_up_card)
            self.current_player = starting_player
        else:
            self.current_player = random.choice(list(self.players.keys()))
    
    def play_cards(self, player_id, cards):
        if not self.game_started or self.current_player != player_id:
            return False, "It's not your turn"
            
        hand = self.players[player_id]['hand']
        for card in cards:
            if card not in hand:
                return False, "You don't have these cards"
                
        is_valid, message = self.validate_play(cards)
        if not is_valid:
            return False, message
            
        for card in cards:
            hand.remove(card)
            
        self.last_played = cards
        
        player_ids = list(self.players.keys())
        current_index = player_ids.index(player_id)
        next_index = (current_index + 1) % len(player_ids)
        self.current_player = player_ids[next_index]
        
        winner = self.check_win_condition()
        if winner:
            self.calculate_scores(winner)
            self.winner = winner
            
        return True, "Cards played successfully"
        
    def pass_turn(self, player_id):
        if not self.game_started or self.current_player != player_id:
            return False, "It's not your turn"
            
        player_ids = list(self.players.keys())
        current_index = player_ids.index(player_id)
        next_index = (current_index + 1) % len(player_ids)
        self.current_player = player_ids[next_index]
        return True, "Turn passed"
        
    def calculate_scores(self, winner):
        for player_id, data in self.players.items():
            if player_id != winner:
                remaining_cards = len(data['hand'])
                self.scores[player_id] = remaining_cards
                self.players[player_id]['score'] = remaining_cards
    
    def validate_play(self, cards):
        if len(cards) == 1:
            return True, ""
            
        if len(cards) == 2:
            if cards[0][0] == cards[1][0]:
                return True, ""
            return False, "Pairs must be of the same rank"
            
        if len(cards) == 5:
            return self.validate_five_card_combination(cards)
            
        if len(cards) == 3:
            return False, "Triples are not allowed"
            
        return False, "Invalid card combination"
        
    def validate_five_card_combination(self, cards):
        rank_order = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2']
        ranks = [card[0] for card in cards]
        suits = [card[1] for card in cards]
        
        sorted_ranks = sorted(ranks, key=lambda x: rank_order.index(x))
        is_straight = True
        for i in range(1, 5):
            if rank_order.index(sorted_ranks[i]) != rank_order.index(sorted_ranks[i-1]) + 1:
                is_straight = False
                break
        if is_straight:
            return True, ""
            
        if len(set(suits)) == 1:
            return True, ""
            
        rank_counts = defaultdict(int)
        for rank in ranks:
            rank_counts[rank] += 1
        if sorted(rank_counts.values()) == [2,3]:
            return True, ""
            
        return False, "Invalid five-card combination"
        
    def check_win_condition(self):
        for player_id, data in self.players.items():
            if len(data['hand']) == 0:
                return player_id
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_game', methods=['POST'])
def create_game():
    player_name = request.json.get('player_name')
    room_id = str(random.randint(1000, 9999))
    games[room_id] = BigTwoGame(room_id)
    player_id = str(random.randint(100000, 999999))
    games[room_id].add_player(player_id, player_name)
    session['player_id'] = player_id
    session['room_id'] = room_id
    return jsonify({
        'room_id': room_id,
        'player_id': player_id
    })

@app.route('/join_game', methods=['POST'])
def join_game():
    room_id = request.json.get('room_id')
    player_name = request.json.get('player_name')
    
    if room_id not in games:
        return jsonify({'error': 'Game not found'}), 404
        
    game = games[room_id]
    player_id = str(random.randint(100000, 999999))
    if not game.add_player(player_id, player_name):
        return jsonify({'error': 'Game is full'}), 400
        
    session['player_id'] = player_id
    session['room_id'] = room_id
    return jsonify({
        'room_id': room_id,
        'player_id': player_id
    })

@app.route('/ready', methods=['POST'])
def ready():
    room_id = session.get('room_id')
    player_id = session.get('player_id')
    
    if room_id not in games or player_id not in games[room_id].players:
        return jsonify({'error': 'Invalid game or player'}), 400
        
    games[room_id].players[player_id]['ready'] = True
    
    game = games[room_id]
    ready_players = sum(1 for p in game.players.values() if p['ready'])
    
    if ready_players >= game.min_players:
        return jsonify({
            'show_face_up_card': True,
            'face_up_card': game.face_up_card,
            'game_started': False
        })
    
    return jsonify({
        'game_started': False,
        'show_face_up_card': False
    })

@app.route('/start_game', methods=['POST'])
def start_game():
    room_id = session.get('room_id')
    player_id = session.get('player_id')
    
    if room_id not in games or player_id not in games[room_id].players:
        return jsonify({'error': 'Invalid game or player'}), 400
        
    game_started = games[room_id].start_game()
    
    return jsonify({
        'game_started': game_started,
        'current_player': games[room_id].current_player if game_started else None
    })

@app.route('/game_state', methods=['GET'])
def game_state():
    room_id = session.get('room_id')
    player_id = session.get('player_id')
    
    if room_id not in games or player_id not in games[room_id].players:
        return jsonify({'error': 'Invalid game or player'}), 400
        
    game = games[room_id]
    opponents = {pid: data for pid, data in game.players.items() if pid != player_id}
    
    return jsonify({
        'hand': game.players[player_id]['hand'],
        'opponents': [{
            'name': data['name'],
            'card_count': len(data['hand']),
            'score': data.get('score', 0)
        } for pid, data in opponents.items()],
        'current_player': game.current_player,
        'last_played': game.last_played,
        'game_started': game.game_started,
        'is_current_player': game.current_player == player_id,
        'scores': game.scores,
        'winner': game.winner
    })

@socketio.on('connect')
def handle_connect():
    player_id = session.get('player_id')
    room_id = session.get('room_id')
    if player_id and room_id:
        join_room(room_id)

@socketio.on('play_cards')
def handle_play_cards(data):
    room_id = session.get('room_id')
    player_id = session.get('player_id')
    
    if room_id not in games or player_id not in games[room_id].players:
        return
        
    game = games[room_id]
    cards = data.get('cards')
    success, message = game.play_cards(player_id, cards)
    
    if success:
        emit('game_update', {
            'last_played': cards,
            'current_player': game.current_player,
            'winner': game.winner,
            'scores': game.scores
        }, room=room_id)
    else:
        emit('play_error', {'message': message})

@socketio.on('pass_turn')
def handle_pass_turn():
    room_id = session.get('room_id')
    player_id = session.get('player_id')
    
    if room_id not in games or player_id not in games[room_id].players:
        return
        
    game = games[room_id]
    success, message = game.pass_turn(player_id)
    
    if success:
        emit('game_update', {
            'last_played': None,
            'current_player': game.current_player
        }, room=room_id)
    else:
        emit('play_error', {'message': message})

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=10000, allow_unsafe_werkzeug=True)
