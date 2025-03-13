/**
 * Подключаем модуль автоматического распознавания речи (ASR)
 */
require(Modules.ASR);

/**
 * Класс для управления событиями
 */
class EventEmitter {
  constructor() {
    this.events = {};
  }

  /**
   * Подписка на событие
   * @param {string} event - Название события
   * @param {Function} listener - Функция-обработчик
   */
  on(event, listener) {
    if (!this.events[event]) {
      this.events[event] = [];
    }
    this.events[event].push(listener);
  }

  /**
   * Вызов события
   * @param {string} event - Название события
   * @param {...any} args - Аргументы обработчика
   */
  emit(event, ...args) {
    if (this.events[event]) {
      this.events[event].forEach(listener => {
        listener(...args);
      });
    }
  }

  /**
   * Отписка от события
   * @param {string} event - Название события
   * @param {Function} listener - Функция-обработчик
   */
  off(event, listener) {
    if (this.events[event]) {
      this.events[event] = this.events[event].filter(l => l !== listener);
    }
  }

  /**
   * Подписка на событие с однократным срабатыванием
   * @param {string} event - Название события
   * @param {Function} listener - Функция-обработчик
   */
  once(event, listener) {
    const onceListener = (...args) => {
      listener(...args);
      this.off(event, onceListener);
    };
    this.on(event, onceListener);
  }
}

/**
 * Класс управления очередью воспроизведения голосовых сообщений
 */
class Player extends EventEmitter {
  constructor() {
    super();
    this.queue = [];  // Очередь текстовых чанков
    this.status = false; // Флаг состояния плеера (играет/не играет)
  }

  /**
   * Запуск воспроизведения
   */
  play() {
    if (!this.status) {
      this.status = true;
      this.emit('play');
    }
  }

  /**
   * Остановка воспроизведения
   */
  stop() {
    if (this.status) {
      this.status = false;
      this.emit('stop');
    }
  }

  /**
   * Добавление текста в очередь
   * @param {string} chank - Текстовый чанк
   */
  add(chank) {
    this.queue.push(chank);
    this.emit('added', chank);
    Logger.write("🎵 Добавлен новый чанк в очередь: " + chank);
  }

  /**
   * Удаление первого элемента из очереди
   * @returns {string|null} - Возвращает удаленный чанк или null
   */
  remove() {
    const chank = this.queue.shift();
    if (chank) {
      this.emit('removed', chank);
      Logger.write("🗑 Удалён чанк из очереди: " + chank);
    }
    return chank;
  }

  /**
   * Очистка очереди
   */
  clear() {
    if (this.queue.length > 0) {
      this.queue = [];
      this.emit('cleared');
      Logger.write("🚮 Очередь полностью очищена");
    }
  }

  /**
   * Переключение состояния (воспроизведение/остановка)
   */
  toggle() {
    this.status ? this.stop() : this.play();
  }

  /**
   * Проверка состояния плеера
   * @returns {boolean}
   */
  get isPlaying() {
    return this.status;
  }

  /**
   * Получение длины очереди
   * @returns {number}
   */
  get length() {
    return this.queue.length;
  }
}

// --- Основные переменные ---
var call, player, asr;
const defaultVoice = VoiceList.TBank.ru_RU_Alyona;
const wsUrl = 'wss://voximplant.onrender.com/ws';
var wsReady = false; // Флаг состояния WebSocket
const voicePlayer = new Player();

// Подписка на событие удаления из очереди
voicePlayer.on('removed', (text) => {
  playNextChunk(text);
});

/**
 * Воспроизведение следующего текстового чанка
 * @param {string} text - Текстовый чанк
 */
async function playNextChunk(text) {
  Logger.write("▶️ Начинаем воспроизведение: " + text);

  player = VoxEngine.createTTSPlayer(text, { language: defaultVoice });
  player.sendMediaTo(call);

  player.addEventListener(PlayerEvents.PlaybackFinished, () => {
    Logger.write("🔚 Воспроизведение завершено: " + text);
    voicePlayer.remove();
  });
}

/**
 * Обработчик входящего вызова
 */
VoxEngine.addEventListener(AppEvents.CallAlerting, (e) => {
  call = e.call;
  Logger.write("📞 Входящий вызов: " + call.id);
  asr = VoxEngine.createASR({ profile: ASRProfileList.TBank.ru_RU, singleUtterance: true });

  const socket = VoxEngine.createWebSocket(wsUrl);
  socket.addEventListener(WebSocketEvents.OPEN, () => wsReady = true);
  socket.addEventListener(WebSocketEvents.MESSAGE, (event) => {
    if (event.text) {
      voicePlayer.add(event.text);
      if (!voicePlayer.isPlaying) {
        voicePlayer.play();
        voicePlayer.remove();
      }
    }
  });

  asr.addEventListener(ASREvents.Result, (e) => {
    if (e.text && wsReady) {
      socket.send(e.text);
      voicePlayer.stop();
      voicePlayer.clear();
    }
  });

  call.addEventListener(CallEvents.Connected, () => {
    player = VoxEngine.createTTSPlayer('Здравствуйте, Вы позвонили в компанию ai-one, чем я могу помочь?', { language: defaultVoice });
    player.sendMediaTo(call);
    player.addEventListener(PlayerEvents.PlaybackMarkerReached, () => call.sendMediaTo(asr));
  });

  call.addEventListener(CallEvents.Disconnected, () => VoxEngine.terminate());
  call.answer();
});
