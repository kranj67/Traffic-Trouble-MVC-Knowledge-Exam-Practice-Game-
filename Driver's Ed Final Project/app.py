import os
from flask import Flask, jsonify, render_template, request
from race import RaceManager, GameError, QUESTIONS

app = Flask(__name__)
manager = RaceManager()


def body():
    return request.get_json(silent=True) or {}


def auth():
    return request.headers.get('X-Player-Token', '')


@app.errorhandler(GameError)
def game_error(err):
    return jsonify(error=str(err)), err.status


@app.get('/')
def index():
    return render_template('index.html')


@app.post('/api/rooms')
def create_room():
    code, token = manager.create(body().get('name'))
    return jsonify(code=code, token=token), 201


@app.post('/api/rooms/<code>/join')
def join_room(code):
    new_code, token = manager.join(code, body().get('name'))
    return jsonify(code=new_code, token=token), 201


@app.post('/api/rooms/<code>/leave')
def leave_room(code):
    return jsonify(manager.leave(code, auth()))


@app.post('/api/rooms/<code>/start')
def start_room(code):
    return jsonify(manager.start(code, auth()))


@app.get('/api/rooms/<code>')
def room_state(code):
    return jsonify(manager.state(code, auth()))


@app.post('/api/rooms/<code>/answer')
def answer(code):
    return jsonify(manager.answer(code, auth(), body().get('choice')))


@app.post('/api/rooms/<code>/next')
def next_question(code):
    return jsonify(manager.next(code, auth()))


@app.get('/health')
def health():
    return jsonify(ok=True, questions=len(QUESTIONS))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5050')), threaded=True, debug=False)
