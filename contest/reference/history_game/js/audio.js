/**
 * 场景音效引擎 - 基于 Web Audio API 纯合成
 * 无需任何外部音频文件，所有声音程序生成
 */

const AmbientAudio = {
    ctx: null,
    masterGain: null,
    layers: [],
    enabled: true,
    initialized: false,

    init() {
        try {
            this.ctx = new (window.AudioContext || window.webkitAudioContext)();
            this.masterGain = this.ctx.createGain();
            this.masterGain.gain.value = 0.3;
            this.masterGain.connect(this.ctx.destination);
            this.initialized = true;
        } catch (e) {
            console.warn('Web Audio API 不可用:', e);
        }
    },

    resume() {
        if (this.ctx && this.ctx.state === 'suspended') {
            this.ctx.resume();
        }
    },

    // ============================================
    // 音效层定义
    // ============================================
    stopAll() {
        this.layers.forEach(layer => {
            try {
                if (layer.osc) { layer.osc.stop(); layer.osc.disconnect(); }
                if (layer.noiseNode) { layer.noiseNode.stop(); layer.noiseNode.disconnect(); }
                if (layer.gain) { layer.gain.disconnect(); }
                if (layer.filter) { layer.filter.disconnect(); }
            } catch(e) {}
        });
        this.layers = [];
    },

    // 白噪声生成器
    createNoise(duration = 2) {
        if (!this.ctx) return null;
        const bufferSize = this.ctx.sampleRate * duration;
        const buffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
            data[i] = Math.random() * 2 - 1;
        }
        const source = this.ctx.createBufferSource();
        source.buffer = buffer;
        source.loop = true;
        return source;
    },

    // ============================================
    // 各场景音效
    // ============================================

    // 养心殿：沉闷的宫殿氛围 - 低频嗡鸣 + 偶尔的风声
    playYangxindian() {
        this.stopAll();
        if (!this.initialized) return;
        this.resume();

        // 低频基底（宫殿回响感）
        const osc1 = this.ctx.createOscillator();
        osc1.type = 'sine';
        osc1.frequency.value = 55; // 低沉的A1
        const gain1 = this.ctx.createGain();
        gain1.gain.value = 0.06;
        osc1.connect(gain1);
        gain1.connect(this.masterGain);
        osc1.start();
        this.layers.push({ osc: osc1, gain: gain1 });

        // 次低频（空旷感）
        const osc2 = this.ctx.createOscillator();
        osc2.type = 'sine';
        osc2.frequency.value = 82;
        const gain2 = this.ctx.createGain();
        gain2.gain.value = 0.03;
        osc2.connect(gain2);
        gain2.connect(this.masterGain);
        osc2.start();
        this.layers.push({ osc: osc2, gain: gain2 });

        // 偶尔的"烛火噼啪" - 用短促的高频噪声脉冲模拟
        this._playCrackle();
    },

    _playCrackle() {
        if (!this.ctx || !this.enabled) return;
        const noise = this.createNoise(0.15);
        const filter = this.ctx.createBiquadFilter();
        filter.type = 'highpass';
        filter.frequency.value = 3000;
        const gain = this.ctx.createGain();
        gain.gain.value = 0;
        noise.connect(filter);
        filter.connect(gain);
        gain.connect(this.masterGain);
        noise.start();

        const now = this.ctx.currentTime;
        gain.gain.setValueAtTime(0, now);
        gain.gain.linearRampToValueAtTime(0.08, now + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);

        noise.stop(now + 0.15);

        // 随机间隔再次触发
        const nextDelay = 3000 + Math.random() * 8000;
        this._crackleTimer = setTimeout(() => this._playCrackle(), nextDelay);
    },

    // 午门外：远处的炮声 + 风声 + 低沉的轰鸣
    playGongmen() {
        this.stopAll();
        if (!this.initialized) return;
        this.resume();

        // 持续低频轰鸣（远处的炮声基底）
        const noise = this.createNoise(4);
        const filter = this.ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 80;
        const gain = this.ctx.createGain();
        gain.gain.value = 0.12;
        noise.connect(filter);
        filter.connect(gain);
        gain.connect(this.masterGain);
        noise.start();
        this.layers.push({ noiseNode: noise, gain: gain, filter: filter });

        // 风声 - 中频噪声
        const wind = this.createNoise(6);
        const windFilter = this.ctx.createBiquadFilter();
        windFilter.type = 'bandpass';
        windFilter.frequency.value = 400;
        windFilter.Q.value = 0.5;
        const windGain = this.ctx.createGain();
        windGain.gain.value = 0.05;

        // 风声的起伏
        const lfo = this.ctx.createOscillator();
        lfo.type = 'sine';
        lfo.frequency.value = 0.15;
        const lfoGain = this.ctx.createGain();
        lfoGain.gain.value = 0.03;
        lfo.connect(lfoGain);
        lfoGain.connect(windGain.gain);
        lfo.start();

        wind.connect(windFilter);
        windFilter.connect(windGain);
        windGain.connect(this.masterGain);
        wind.start();
        this.layers.push({ noiseNode: wind, gain: windGain, filter: windFilter, osc: lfo });

        // 定期模拟远处炮声
        this._playDistantCannon();
    },

    _playDistantCannon() {
        if (!this.ctx || !this.enabled) return;
        const now = this.ctx.currentTime;

        // 炮声：低频爆裂 + 衰减
        const osc = this.ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(60, now);
        osc.frequency.exponentialRampToValueAtTime(20, now + 0.8);
        const oscGain = this.ctx.createGain();
        oscGain.gain.setValueAtTime(0.25, now);
        oscGain.gain.exponentialRampToValueAtTime(0.001, now + 1.2);
        osc.connect(oscGain);
        oscGain.connect(this.masterGain);
        osc.start(now);
        osc.stop(now + 1.5);

        // 噪声层（冲击波）
        const noise = this.createNoise(1.5);
        const nFilter = this.ctx.createBiquadFilter();
        nFilter.type = 'lowpass';
        nFilter.frequency.setValueAtTime(500, now);
        nFilter.frequency.exponentialRampToValueAtTime(50, now + 1.0);
        const nGain = this.ctx.createGain();
        nGain.gain.setValueAtTime(0.15, now);
        nGain.gain.exponentialRampToValueAtTime(0.001, now + 1.2);
        noise.connect(nFilter);
        nFilter.connect(nGain);
        nGain.connect(this.masterGain);
        noise.start(now);
        noise.stop(now + 1.5);

        // 随机间隔下一次炮声（5-15秒）
        const nextDelay = 5000 + Math.random() * 10000;
        this._cannonTimer = setTimeout(() => this._playDistantCannon(), nextDelay);
    },

    // 驿站：仓皇混乱 - 马嘶 + 风声 + 远处低沉的哭声
    playYizhan() {
        this.stopAll();
        if (!this.initialized) return;
        this.resume();

        // 风声（比午门外更冷更急）
        const wind = this.createNoise(5);
        const windFilter = this.ctx.createBiquadFilter();
        windFilter.type = 'bandpass';
        windFilter.frequency.value = 500;
        windFilter.Q.value = 0.8;
        const windGain = this.ctx.createGain();
        windGain.gain.value = 0.07;

        const lfo = this.ctx.createOscillator();
        lfo.type = 'sine';
        lfo.frequency.value = 0.25;
        const lfoGain = this.ctx.createGain();
        lfoGain.gain.value = 0.04;
        lfo.connect(lfoGain);
        lfoGain.connect(windGain.gain);
        lfo.start();

        wind.connect(windFilter);
        windFilter.connect(windGain);
        windGain.connect(this.masterGain);
        wind.start();
        this.layers.push({ noiseNode: wind, gain: windGain, filter: windFilter, osc: lfo });

        // 低沉的嘈杂基底（人群低语/哭泣）
        const crowd = this.createNoise(3);
        const crowdFilter = this.ctx.createBiquadFilter();
        crowdFilter.type = 'bandpass';
        crowdFilter.frequency.value = 600;
        crowdFilter.Q.value = 1;
        const crowdGain = this.ctx.createGain();
        crowdGain.gain.value = 0.03;
        crowd.connect(crowdFilter);
        crowdFilter.connect(crowdGain);
        crowdGain.connect(this.masterGain);
        crowd.start();
        this.layers.push({ noiseNode: crowd, gain: crowdGain, filter: crowdFilter });

        // 偶尔的马嘶声
        this._playHorseWhinny();
    },

    _playHorseWhinny() {
        if (!this.ctx || !this.enabled) return;
        const now = this.ctx.currentTime;
        // 马嘶：高频起音 + 滑降
        const osc = this.ctx.createOscillator();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(800, now);
        osc.frequency.linearRampToValueAtTime(1200, now + 0.1);
        osc.frequency.exponentialRampToValueAtTime(300, now + 0.5);
        const oscGain = this.ctx.createGain();
        oscGain.gain.setValueAtTime(0.06, now);
        oscGain.gain.linearRampToValueAtTime(0.08, now + 0.05);
        oscGain.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
        const filter = this.ctx.createBiquadFilter();
        filter.type = 'bandpass';
        filter.frequency.value = 1000;
        filter.Q.value = 2;
        osc.connect(filter);
        filter.connect(oscGain);
        oscGain.connect(this.masterGain);
        osc.start(now);
        osc.stop(now + 0.6);

        // 随机间隔
        const nextDelay = 4000 + Math.random() * 12000;
        this._horseTimer = setTimeout(() => this._playHorseWhinny(), nextDelay);
    },

    // 避暑山庄：萧瑟秋风 + 远处戏腔 + 寂寥
    playBishushanzhuang() {
        this.stopAll();
        if (!this.initialized) return;
        this.resume();

        // 秋风（塞外更冷）
        const wind = this.createNoise(6);
        const windFilter = this.ctx.createBiquadFilter();
        windFilter.type = 'bandpass';
        windFilter.frequency.value = 350;
        windFilter.Q.value = 0.3;
        const windGain = this.ctx.createGain();
        windGain.gain.value = 0.06;

        const lfo = this.ctx.createOscillator();
        lfo.type = 'sine';
        lfo.frequency.value = 0.1;
        const lfoGain = this.ctx.createGain();
        lfoGain.gain.value = 0.04;
        lfo.connect(lfoGain);
        lfoGain.connect(windGain.gain);
        lfo.start();

        wind.connect(windFilter);
        windFilter.connect(windGain);
        windGain.connect(this.masterGain);
        wind.start();
        this.layers.push({ noiseNode: wind, gain: windGain, filter: windFilter, osc: lfo });

        // 极低频基底（空旷感）
        const osc = this.ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.value = 40;
        const oscGain = this.ctx.createGain();
        oscGain.gain.value = 0.04;
        osc.connect(oscGain);
        oscGain.connect(this.masterGain);
        osc.start();
        this.layers.push({ osc: osc, gain: oscGain });

        // 偶尔的鸟鸣（用高频短促音模拟）
        this._playBird();
    },

    _playBird() {
        if (!this.ctx || !this.enabled) return;
        const now = this.ctx.currentTime;
        const osc = this.ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(2000, now);
        osc.frequency.linearRampToValueAtTime(2500, now + 0.05);
        osc.frequency.linearRampToValueAtTime(1800, now + 0.15);
        osc.frequency.linearRampToValueAtTime(2200, now + 0.2);
        const gain = this.ctx.createGain();
        gain.gain.setValueAtTime(0.02, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
        osc.connect(gain);
        gain.connect(this.masterGain);
        osc.start(now);
        osc.stop(now + 0.3);

        const nextDelay = 6000 + Math.random() * 15000;
        this._birdTimer = setTimeout(() => this._playBird(), nextDelay);
    },

    // 烟波致爽殿：极度安静 + 偶尔咳嗽 + 风声
    playYanbozhishuang() {
        this.stopAll();
        if (!this.initialized) return;
        this.resume();

        // 极轻的风声
        const wind = this.createNoise(5);
        const windFilter = this.ctx.createBiquadFilter();
        windFilter.type = 'bandpass';
        windFilter.frequency.value = 250;
        windFilter.Q.value = 0.2;
        const windGain = this.ctx.createGain();
        windGain.gain.value = 0.02;
        wind.connect(windFilter);
        windFilter.connect(windGain);
        windGain.connect(this.masterGain);
        wind.start();
        this.layers.push({ noiseNode: wind, gain: windGain, filter: windFilter });

        // 极低频（沉寂）
        const osc = this.ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.value = 35;
        const oscGain = this.ctx.createGain();
        oscGain.gain.value = 0.03;
        osc.connect(oscGain);
        oscGain.connect(this.masterGain);
        osc.start();
        this.layers.push({ osc: osc, gain: oscGain });

        // 偶尔的咳嗽声
        this._playCough();
    },

    _playCough() {
        if (!this.ctx || !this.enabled) return;
        const now = this.ctx.currentTime;

        // 咳嗽：短促噪声脉冲 x2
        for (let i = 0; i < 2; i++) {
            const offset = i * 0.25;
            const noise = this.createNoise(0.12);
            const filter = this.ctx.createBiquadFilter();
            filter.type = 'bandpass';
            filter.frequency.value = 800 + i * 200;
            filter.Q.value = 1.5;
            const gain = this.ctx.createGain();
            gain.gain.setValueAtTime(0, now + offset);
            gain.gain.linearRampToValueAtTime(0.06, now + offset + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.1);
            noise.connect(filter);
            filter.connect(gain);
            gain.connect(this.masterGain);
            noise.start(now + offset);
            noise.stop(now + offset + 0.15);
        }

        const nextDelay = 8000 + Math.random() * 20000;
        this._coughTimer = setTimeout(() => this._playCough(), nextDelay);
    },

    // ============================================
    // 按场景ID播放
    // ============================================
    playScene(sceneId) {
        if (!this.enabled) return;
        this._clearTimers();

        switch (sceneId) {
            case 'yangxindian':
                this.playYangxindian();
                break;
            case 'gongmen':
                this.playGongmen();
                break;
            case 'yizhan':
                this.playYizhan();
                break;
            case 'bishushanzhuang':
                this.playBishushanzhuang();
                break;
            case 'yanbozhishuang':
                this.playYanbozhishuang();
                break;
            default:
                this.playYangxindian();
        }
    },

    _clearTimers() {
        if (this._crackleTimer) clearTimeout(this._crackleTimer);
        if (this._cannonTimer) clearTimeout(this._cannonTimer);
        if (this._horseTimer) clearTimeout(this._horseTimer);
        if (this._birdTimer) clearTimeout(this._birdTimer);
        if (this._coughTimer) clearTimeout(this._coughTimer);
    },

    toggle() {
        this.enabled = !this.enabled;
        if (!this.enabled) {
            this._clearTimers();
            this.stopAll();
        }
        return this.enabled;
    },

    setVolume(v) {
        if (this.masterGain) {
            this.masterGain.gain.value = Math.max(0, Math.min(1, v));
        }
    }
};