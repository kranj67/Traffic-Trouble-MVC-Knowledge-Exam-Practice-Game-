from __future__ import annotations

import json
import random
import re
import secrets
import threading
import time
from pathlib import Path

QUESTIONS = json.loads(
    (Path(__file__).parent / 'data' / 'questions.json')
    .read_text(encoding='utf-8')
)

assert len(QUESTIONS) == 30
assert all(len(q['options']) == 4 for q in QUESTIONS)

QUESTIONS_PER_RACE = 15
PENALTY_SECONDS = 8
COUNTDOWN_SECONDS = 4
MAX_PLAYERS = 30

ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

class GameError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

class RaceManager:
    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.rooms = {}
        self.lock = threading.RLock()

    def create(self, name):
        name = self._name(name)

        with self.lock:

            if len(self.rooms) >= 150:
                raise GameError(
                    'Server has too many rooms. Restart the app.'
                )

            # room code
            code = ''.join(
                secrets.choice(ALPHABET)
                for _ in range(5)
            )

            while code in self.rooms:
                code = ''.join(
                    secrets.choice(ALPHABET)
                    for _ in range(5)
                )

            token = secrets.token_urlsafe(24)
            player = self._player(name, token)

            chapters = sorted({
                q['chapter'] for q in QUESTIONS
            })

            selected_questions = [
                random.choice([
                    q for q in QUESTIONS
                    if q['chapter'] == chapter
                ])
                for chapter in chapters
            ]

            remaining = [
                q for q in QUESTIONS
                if q not in selected_questions
            ]

            selected_questions.extend(
                random.sample(
                    remaining,
                    QUESTIONS_PER_RACE
                    - len(selected_questions)
                )
            )

            random.shuffle(selected_questions)

            self.rooms[code] = {
                'code': code,
                'host': token,
                'players': {
                    token: player
                },
                'started_at': None,
                'created_at': self.clock(),
                'questions': selected_questions
            }

            return code, token

    def join(self, code, name):
        name = self._name(name)

        with self.lock:
            room = self._room(code)

            if room['started_at'] is not None:
                raise GameError(
                    'This race already started.'
                )

            if len(room['players']) >= MAX_PLAYERS:
                raise GameError('This room is full.')

            if any(
                p['name'].casefold() == name.casefold()
                for p in room['players'].values()
            ):
                raise GameError(
                    'That name is already taken.'
                )

            token = secrets.token_urlsafe(24)

            room['players'][token] = self._player(
                name, token
            )

            return room['code'], token

    def leave(self, code, token):

        with self.lock:
            room = self._authorize(code, token)

            del room['players'][token]

            if not room['players']:
                del self.rooms[room['code']]

            elif room['host'] == token:
                room['host'] = next(
                    iter(room['players'])
                )

            return {'left': True}

    def start(self, code, token):

        with self.lock:
            room = self._authorize(code, token)

            if room['host'] != token:
                raise GameError(
                    'Only the host can start the race.',
                    403
                )

            if room['started_at'] is not None:
                raise GameError(
                    'The race has already started.'
                )

            room['started_at'] = (
                self.clock() + COUNTDOWN_SECONDS
            )

            return self._state(room, token)

    def answer(self, code, token, choice):

        with self.lock:
            room = self._authorize(code, token)
            player = room['players'][token]

            if (
                room['started_at'] is None
                or self.clock() < room['started_at']
            ):
                raise GameError(
                    'Wait for the race to start.'
                )

            if player['finished_at'] is not None:
                raise GameError(
                    'You have finished the race.'
                )

            if player['pending'] is not None:
                raise GameError(
                    'Continue to the next question first.'
                )

            if (
                type(choice) is not int
                or not 0 <= choice <= 3
            ):
                raise GameError(
                    'Choose an answer from A to D.'
                )

            question = room['questions'][
                player['index']
            ]

            right = (
                choice == question['answer']
            )

            if right:
                player['correct'] += 1

            else:
                player['penalty'] += PENALTY_SECONDS
                player['tickets'] += 1

            player['pending'] = {
                'correct': right,

                'answer': question['options'][
                    question['answer']
                ],

                'explanation': question[
                    'explanation'
                ],

                'source': (
                    f"Chapter {question['chapter']}, "
                    f"page {question['page']}"
                ),

                'penaltyAdded': (
                    0 if right
                    else PENALTY_SECONDS
                )
            }

            if (
                player['index']
                == len(room['questions']) - 1
            ):
                player['finished_at'] = self.clock()

            return self._state(room, token)

    def next(self, code, token):

        with self.lock:
            room = self._authorize(code, token)
            player = room['players'][token]

            if player['pending'] is None:
                raise GameError(
                    'Answer the question first.'
                )

            if player['finished_at'] is not None:
                raise GameError(
                    'The race is already complete.'
                )

            player['index'] += 1
            player['pending'] = None

            return self._state(room, token)

    def state(self, code, token):

        with self.lock:
            room = self._authorize(code, token)
            return self._state(room, token)

    @staticmethod
    def _name(name):

        if not isinstance(name, str):
            raise GameError(
                'Enter a player name.'
            )

        name = name.strip()

        if not re.fullmatch(
            r'[\w .-]{1,18}',
            name,
            flags=re.UNICODE
        ):
            raise GameError(
                'Name must be 1–18 letters, numbers, '
                'spaces, dots, or dashes.'
            )

        return name

    @staticmethod
    def _player(name, token):

        return {
            'name': name,
            'token': token,
            'index': 0,
            'pending': None,
            'correct': 0,
            'tickets': 0,
            'penalty': 0,
            'finished_at': None
        }

    def _room(self, code):

        room = self.rooms.get(
            str(code).strip().upper()
        )

        if room is None:
            raise GameError(
                'Room not found. Check the room code.',
                404
            )

        return room

    def _authorize(self, code, token):

        room = self._room(code)

        if (
            not token
            or token not in room['players']
        ):
            raise GameError(
                'You are not a player in this room.',
                403
            )

        return room

    def _state(self, room, token):

        player = room['players'][token]

        now = self.clock()
        started = room['started_at']

        if started is None:
            phase = 'lobby'

        elif now < started:
            phase = 'countdown'

        else:
            phase = 'racing'

        scores = []

        for p in room['players'].values():

            progress = (
                p['index']
                + (p['pending'] is not None)
            )

            if started is not None:

                end_time = (
                    p['finished_at']
                    if p['finished_at'] is not None
                    else now
                )

                elapsed = max(
                    0.0,
                    end_time - started
                )

            else:
                elapsed = 0.0

            final_time = round(
                elapsed + p['penalty'],
                1
            )

            scores.append({
                'name': p['name'],
                'progress': progress,
                'correct': p['correct'],
                'tickets': p['tickets'],
                'penalty': p['penalty'],
                'adjusted': final_time,
                'finished': (
                    p['finished_at'] is not None
                )
            })

        scores.sort(
            key=lambda s: (
                -s['progress'],
                s['adjusted'],
                s['name'].casefold()
            )
        )

        all_finished = (
            started is not None
            and now >= started
            and all(
                p['finished_at'] is not None
                for p in room['players'].values()
            )
        )

        winner = None

        if all_finished and scores:

            winner = {
                'name': scores[0]['name'],
                'time': scores[0]['adjusted'],
                'tickets': scores[0]['tickets']
            }

        count = (
            player['index']
            + (player['pending'] is not None)
        )

        question = None

        if (
            phase == 'racing'
            and player['pending'] is None
            and player['finished_at'] is None
        ):

            q = room['questions'][
                player['index']
            ]

            question = {
                'number': player['index'] + 1,
                'chapter': q['chapter'],
                'question': q['question'],
                'options': q['options']
            }

        return {
            'room': room['code'],
            'phase': phase,
            'host': token == room['host'],
            'name': player['name'],

            'countdown': (
                round(max(0, started - now), 1)
                if started is not None
                else None
            ),

            'progress': count,
            'total': len(room['questions']),

            'correct': player['correct'],
            'tickets': player['tickets'],
            'penalty': player['penalty'],

            'finished': (
                player['finished_at'] is not None
            ),

            'pending': player['pending'],
            'question': question,

            'leaderboard': scores,

            'allFinished': all_finished,
            'winner': winner,

            'playerCount': len(scores)
        }