const $ = id => document.getElementById(id);

let credentials = null;
let previousView = '';
let busy = false;
let dismissedFinalFeedback = false;
let polling = false;

function showError(message) {
  $('error').textContent = message;
  $('error').hidden = !message;
}

function panel(id, visible) {
  $(id).hidden = !visible;
}

function formatSeconds(value) {
  const minutes = Math.floor(value / 60);

  const seconds = (value % 60)
    .toFixed(1)
    .padStart(4, '0');

  return (
    `${String(minutes).padStart(2, '0')}:` +
    seconds
  );
}

async function api(path, method = 'GET', payload) {

  const response = await fetch(path, {
    method,

    headers: {
      'Content-Type': 'application/json',

      ...(credentials ? {
        'X-Player-Token': credentials.token
      } : {})
    },

    ...(payload !== undefined ? {
      body: JSON.stringify(payload)
    } : {}),

    cache: 'no-store'
  });

  const result = await response.json();

  if (!response.ok) {
    throw new Error(
      result.error || 'Something went wrong.'
    );
  }

  return result;
}

async function createOrJoin(join) {

  if (busy) return;

  busy = true;

  try {
    showError('');

    const name = $('name').value.trim();

    const code = $('join-code')
      .value.trim()
      .toUpperCase();

    const url = join
      ? `/api/rooms/${encodeURIComponent(code)}/join`
      : '/api/rooms';

    const result = await api(
      url,
      'POST',
      { name }
    );

    credentials = {
      code: result.code,
      token: result.token
    };

    sessionStorage.setItem(
      'trafficRace',
      JSON.stringify(credentials)
    );

    previousView = '';
    dismissedFinalFeedback = false;

    busy = false;

    await poll();

  } catch (error) {
    showError(error.message);

  } finally {
    busy = false;
  }
}

function reset() {

  credentials = null;
  dismissedFinalFeedback = false;

  sessionStorage.removeItem('trafficRace');

  previousView = '';

  showError('');

  panel('home', true);
  panel('room-screen', false);
}

async function mutate(url, payload) {

  if (busy || !credentials) return;

  busy = true;

  try {
    showError('');

    const result = await api(
      url,
      'POST',
      payload
    );

    render(result);

  } catch (error) {
    showError(error.message);

  } finally {
    busy = false;
  }
}


function renderBoard(data) {

  const board = $('board');

  board.replaceChildren();

  $('player-count').textContent =
    `${data.playerCount} player` +
    `${data.playerCount === 1 ? '' : 's'}`;

  data.leaderboard.forEach((player, index) => {

    const li = document.createElement('li');

    if (player.name === data.name) {
      li.className = 'you';
    }

    const heading = document.createElement('strong');

    heading.textContent =
      `${data.allFinished && index === 0 ? '🏆 ' : ''}` +
      `${player.name}` +
      `${player.finished ? ' 🏁' : ''}`;

    const sub = document.createElement('span');

    sub.textContent =
      `${player.progress}/${data.total} · ` +
      `${formatSeconds(player.adjusted)} · ` +
      `${player.tickets} tickets`;

    li.append(heading, sub);

    board.appendChild(li);
  });
}

function render(data) {

  panel('home', false);
  panel('room-screen', true);

  $('room-code').textContent = data.room;
  $('your-name').textContent = data.name;

  renderBoard(data);

  panel('lobby', data.phase === 'lobby');

  panel(
    'countdown',
    data.phase === 'countdown'
  );

  panel(
    'racing',
    data.phase === 'racing'
  );

  if (data.phase === 'lobby') {

    panel('start', data.host);
    panel('waiting', !data.host);

    return;
  }

  if (data.phase === 'countdown') {

    $('count').textContent = Math.max(
      1,
      Math.ceil(data.countdown)
    );

    return;
  }

  const self = data.leaderboard.find(
    player => player.name === data.name
  );

  $('race-time').textContent =
    formatSeconds(self?.adjusted ?? 0);

  $('progress-text').textContent =
    `${data.progress} / ${data.total} checkpoints`;

  $('penalty-text').textContent =
    `Traffic delays: +${data.penalty}s`;

  const percent = Math.min(
    100,
    100 * data.progress / data.total
  );

  $('road-fill').style.width = `${percent}%`;

  $('car').style.left =
    `${Math.min(95, percent)}%`;

  panel(
    'question-panel',
    !data.pending && !data.finished
  );

  panel(
    'feedback',
    Boolean(data.pending) &&
    !(data.finished && dismissedFinalFeedback)
  );

  panel(
    'finished',
    data.finished &&
    (!data.pending || dismissedFinalFeedback)
  );

  if (data.pending) {

    const result = data.pending;

    $('feedback').classList.toggle(
      'wrong',
      !result.correct
    );

    $('feedback-title').textContent =
      result.correct
        ? 'Correct! Road is clear.'
        : `Traffic delay: +${result.penaltyAdded} seconds`;

    $('feedback-rule').textContent =
      `${result.correct ? '' : `Correct answer: ${result.answer}. `}` +
      result.explanation;

    $('feedback-source').textContent =
      `2025 NJ Driver Manual · ${result.source}`;

    $('next').textContent =
      data.finished
        ? 'See my result'
        : 'Continue driving →';
  }

  if (data.finished) {

    $('finish-stats').textContent =
      `Final time: ${formatSeconds(self.adjusted)} · ` +
      `${data.tickets} tickets`;

    if (data.allFinished && data.winner) {

      $('finish-title').textContent =
        data.winner.name === data.name
          ? '🏆 You won!'
          : `🏆 ${data.winner.name} wins!`;

      $('finish-status').textContent =
        `Winning time: ${formatSeconds(data.winner.time)} · ` +
        `${data.winner.tickets} tickets`;

      panel('new-room', true);

    } else {

      $('finish-title').textContent =
        '🏁 Completed';

      $('finish-status').textContent =
        'Waiting for others to finish…';

      panel('new-room', false);
    }
  }

  const viewKey =
    `${data.phase}:${data.progress}:` +
    `${Boolean(data.pending)}:${data.finished}`;

  if (
    !data.pending &&
    !data.finished &&
    data.question &&
    previousView !== viewKey
  ) {

    $('question-label').textContent =
      `QUESTION ${data.question.number} OF ${data.total} · ` +
      `CHAPTER ${data.question.chapter}`;

    $('question').textContent =
      data.question.question;

    $('choices').replaceChildren();

    data.question.options.forEach(
      (option, i) => {

        const button = document.createElement(
          'button'
        );

        button.textContent =
          `${'ABCD'[i]}. ${option}`;

        button.addEventListener(
          'click',
          () => mutate(
            `/api/rooms/${credentials.code}/answer`,
            { choice: i }
          )
        );

        $('choices').appendChild(button);
      }
    );
  }

  previousView = viewKey;
}

async function poll() {

  if (!credentials || busy || polling) return;

  polling = true;

  try {

    const data = await api(
      `/api/rooms/${credentials.code}`
    );

    showError('');

    render(data);

  } catch (error) {

    if (
      /not a player|room not found/i.test(
        error.message
      )
    ) {
      reset();
    }

    showError(error.message);

  } finally {
    polling = false;
  }
}

$('create').addEventListener(
  'click',
  () => createOrJoin(false)
);

$('join').addEventListener(
  'click',
  () => createOrJoin(true)
);

$('start').addEventListener(
  'click',
  () => mutate(
    `/api/rooms/${credentials.code}/start`
  )
);

$('next').addEventListener('click', () => {

  if (!credentials) return;

  const isLast =
    $('next').textContent === 'See my result';

  if (isLast) {
    dismissedFinalFeedback = true;

    panel('feedback', false);
    panel('finished', true);

    poll();
  } else {

    mutate(
      `/api/rooms/${credentials.code}/next`
    );
  }
});

$('leave').addEventListener(
  'click',
  async () => {

    if (credentials) {

      try {
        await api(
          `/api/rooms/${credentials.code}/leave`,
          'POST'
        );
      } catch {}
    }

    reset();
  }
);

$('new-room').addEventListener(
  'click',
  async () => {

    if (credentials) {

      try {
        await api(
          `/api/rooms/${credentials.code}/leave`,
          'POST'
        );
      } catch {}
    }

    reset();
  }
);

// enter to do actions for convience

$('join-code').addEventListener(
  'keydown',
  event => {

    if (event.key === 'Enter') {
      createOrJoin(true);
    }
  }
);


$('name').addEventListener(
  'keydown',
  event => {

    if (event.key === 'Enter') {
      createOrJoin(false);
    }
  }
);

try {

  credentials = JSON.parse(
    sessionStorage.getItem('trafficRace')
    || 'null'
  );

} catch {
  credentials = null;
}

if (credentials?.code && credentials?.token) {
  poll();
}

if (
  new URLSearchParams(location.search)
    .has('room')
) {

  $('join-code').value =
    new URLSearchParams(location.search)
      .get('room')
      .toUpperCase();
}

setInterval(poll, 800);