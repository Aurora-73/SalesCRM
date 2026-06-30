/**
 * 历史沉浸式决策游戏 - 核心引擎
 * 基于 Phaser 3 的 2D 俯视角探索与决策系统
 */

// ============================================
// 决策ID → 目标场景ID 映射
// 当某个决策完成后，自动解锁对应场景
// ============================================
const DECISION_SCENE_MAP = {
    'rehe_001': 'gongmen',       // 养心殿决策后解锁午门外
    'rehe_002': 'yizhan',        // 午门外决策后解锁驿站
    'rehe_003': 'bishushanzhuang', // 驿站决策后解锁热河行宫
    'rehe_004': null              // 烟波致爽殿决策后触发结局，无新场景
};

// ============================================
// 游戏状态管理器
// ============================================
const GameState = {
    currentSceneId: null,
    playerPosition: { x: 0, y: 0 },
    unlockedScenes: ['yangxindian'],
    visitedScenes: [],
    dialogueHistory: [],
    decisionsMade: [],
    knowledgeUnlocked: [],
    score: 0,
    gameStarted: false,
    gameEnded: false,
    narratorEnabled: true,
    idleTime: 0,

    reset() {
        this.currentSceneId = null;
        this.playerPosition = { x: 0, y: 0 };
        this.unlockedScenes = ['yangxindian'];
        this.visitedScenes = [];
        this.dialogueHistory = [];
        this.decisionsMade = [];
        this.knowledgeUnlocked = [];
        this.score = 0;
        this.gameStarted = false;
        this.gameEnded = false;
        this.narratorEnabled = true;
        this.idleTime = 0;
    },

    recordDecision(decisionId, optionId, isAccurate) {
        this.decisionsMade.push({ decisionId, optionId, isAccurate, timestamp: Date.now() });
        if (isAccurate) this.score += 3;
        else this.score += 1;
    },

    recordDialogue(npcId, topicId) {
        this.dialogueHistory.push({ npcId, topicId, timestamp: Date.now() });
    },

    unlockScene(sceneId) {
        if (!this.unlockedScenes.includes(sceneId)) {
            this.unlockedScenes.push(sceneId);
        }
    },

    visitScene(sceneId) {
        if (!this.visitedScenes.includes(sceneId)) {
            this.visitedScenes.push(sceneId);
        }
    }
};

// ============================================
// TTS 旁白配音系统 (Web Speech API)
// ============================================
const TTSNarrator = {
    enabled: true,
    speaking: false,
    synth: window.speechSynthesis || null,
    ttsIndicator: null,

    init() {
        this.ttsIndicator = document.getElementById('tts-indicator');
    },

    // 情感参数映射
    emotions: {
        default:  { rate: 0.88, pitch: 0.95, volume: 0.8 },
        urgent:   { rate: 1.05, pitch: 1.15, volume: 0.92 }, // 紧张、危急
        sad:      { rate: 0.72, pitch: 0.82, volume: 0.65 }, // 悲凉、沉痛
        tempting: { rate: 0.80, pitch: 0.90, volume: 0.78 }, // 蛊惑、引诱
        calm:     { rate: 0.85, pitch: 1.00, volume: 0.75 }, // 平静、叙述
        angry:    { rate: 1.00, pitch: 1.05, volume: 0.88 }, // 愤怒、斥责
        whisper:  { rate: 0.70, pitch: 0.88, volume: 0.55 }  // 耳语、私密
    },

    // 根据文本内容推断情感
    inferEmotion(text) {
        if (/蛊惑|留得青山|走吧|逃|跑路/i.test(text)) return 'tempting';
        if (/惨败|伤亡|崩溃|崩塌|覆灭|病逝|咳血|焚毁/i.test(text)) return 'sad';
        if (/危急|紧迫|逼近|失守|大败|危急存亡/i.test(text)) return 'urgent';
        if (/愤怒|叛逆|荒唐|该死|混账/i.test(text)) return 'angry';
        if (/耳语|悄悄|私下|秘/i.test(text)) return 'whisper';
        return 'default';
    },

    speak(text, onEnd, emotion) {
        if (!this.synth || !this.enabled) {
            if (onEnd) onEnd();
            return;
        }

        // 取消之前的语音
        this.synth.cancel();

        const emo = emotion || this.inferEmotion(text);
        const params = this.emotions[emo] || this.emotions.default;

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'zh-CN';
        utterance.rate = params.rate;
        utterance.pitch = params.pitch;
        utterance.volume = params.volume;

        // 尝试选择中文语音（优先选择女声，更贴合旁白）
        const voices = this.synth.getVoices();
        const zhVoices = voices.filter(v => v.lang.startsWith('zh'));
        // 优先选择 Google 中文或 Microsoft 中文女声
        const preferred = zhVoices.find(v => /female|女|xiaoxiao|xiaoyi/i.test(v.name)) || zhVoices[0];
        if (preferred) utterance.voice = preferred;

        utterance.onstart = () => {
            this.speaking = true;
            if (this.ttsIndicator) this.ttsIndicator.classList.add('active');
        };

        utterance.onend = () => {
            this.speaking = false;
            if (this.ttsIndicator) this.ttsIndicator.classList.remove('active');
            if (onEnd) onEnd();
        };

        utterance.onerror = () => {
            this.speaking = false;
            if (this.ttsIndicator) this.ttsIndicator.classList.remove('active');
            if (onEnd) onEnd();
        };

        this.synth.speak(utterance);
    },

    stop() {
        if (this.synth) this.synth.cancel();
        this.speaking = false;
        if (this.ttsIndicator) this.ttsIndicator.classList.remove('active');
    },

    toggle() {
        this.enabled = !this.enabled;
        this.stop();
        return this.enabled;
    }
};

// 确保语音列表加载
if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
}

// ============================================
// UI 管理器
// ============================================
const UIManager = {
    dialoguePanel: null,
    decisionPanel: null,
    narratorPanel: null,
    endingPanel: null,
    feedbackPanel: null,
    minimapPanel: null,
    historyLogPanel: null,
    geopoliticsPanel: null,
    interactionHint: null,
    controlsHint: null,
    atmosphereOverlay: null,

    init() {
        this.dialoguePanel = document.getElementById('dialogue-panel');
        this.decisionPanel = document.getElementById('decision-panel');
        this.narratorPanel = document.getElementById('narrator-panel');
        this.endingPanel = document.getElementById('ending-panel');
        this.feedbackPanel = document.getElementById('feedback-panel');
        this.minimapPanel = document.getElementById('minimap-panel');
        this.historyLogPanel = document.getElementById('history-log-panel');
        this.geopoliticsPanel = document.getElementById('geopolitics-panel');
        this.interactionHint = document.getElementById('interaction-hint');
        this.controlsHint = document.getElementById('controls-hint');
        this.atmosphereOverlay = document.getElementById('atmosphere-overlay');
        TTSNarrator.init();
    },

    showNarrator(text, duration = 5000, emotion) {
        if (!this.narratorPanel) return;
        const textEl = this.narratorPanel.querySelector('.narrator-text');
        textEl.textContent = text;
        this.narratorPanel.classList.add('active');

        // TTS配音（传入情感参数）
        TTSNarrator.speak(text, null, emotion);

        setTimeout(() => {
            this.narratorPanel.classList.remove('active');
        }, duration);
    },

    // ============================================
    // 国力与国际局势面板
    // ============================================
    showGeopolitics() {
        if (!this.geopoliticsPanel) return;
        if (this.geopoliticsPanel.classList.contains('active')) {
            this.hideGeopolitics();
            return;
        }
        this.renderPowerGrid();
        this.renderThreatList();
        this.renderWarTimeline();
        this.geopoliticsPanel.classList.add('active');
    },

    hideGeopolitics() {
        if (this.geopoliticsPanel) this.geopoliticsPanel.classList.remove('active');
    },

    renderPowerGrid() {
        const grid = document.getElementById('power-grid');
        if (!grid) return;
        grid.innerHTML = '';

        const qp = HISTORY_DATA.geopolitics.qingPower;
        const items = ['finance', 'military', 'population', 'morale'];
        items.forEach(key => {
            const item = qp[key];
            const div = document.createElement('div');
            div.className = 'power-item trend-' + (item.trend || 'down');
            div.innerHTML = `
                <div class="power-label">${item.label}</div>
                <div class="power-value">${item.value}</div>
                <div class="power-detail">${item.detail}<br><small>出处：${item.source}</small></div>
            `;
            grid.appendChild(div);
        });
    },

    renderThreatList() {
        const list = document.getElementById('threat-list');
        if (!list) return;
        list.innerHTML = '';

        HISTORY_DATA.geopolitics.foreignPowers.forEach(power => {
            const div = document.createElement('div');
            div.className = 'threat-item';
            const barWidth = (power.threat / 5 * 100) + '%';
            div.innerHTML = `
                <div class="threat-flag" style="background:${power.color}">${power.flag}</div>
                <div class="threat-info">
                    <div class="threat-name">${power.name}</div>
                    <div class="threat-force">${power.force} · ${power.status}</div>
                    <div class="threat-bar"><div class="threat-bar-fill" style="width:${barWidth};background:${power.color}"></div></div>
                    <div class="threat-detail">
                        <strong>目标：</strong>${power.goal}<br>
                        <strong>位置：</strong>${power.location}<br>
                        <strong>主导者：</strong>${power.source}
                        ${power.detail ? '<br>' + power.detail : ''}
                    </div>
                </div>
            `;
            div.onclick = () => div.classList.toggle('expanded');
            list.appendChild(div);
        });
    },

    renderWarTimeline() {
        const timeline = document.getElementById('war-timeline');
        if (!timeline) return;
        timeline.innerHTML = '';

        HISTORY_DATA.geopolitics.warMap.phases.forEach(phase => {
            const item = document.createElement('div');
            item.className = 'timeline-item';
            item.innerHTML = `
                <div class="timeline-dot ${phase.type}"></div>
                <div class="timeline-label">${phase.label}</div>
                <div class="timeline-event">${phase.event}</div>
            `;
            timeline.appendChild(item);
        });
    },

    // ============================================
    // 场景氛围系统
    // ============================================
    showAtmosphere(sceneId) {
        if (!this.atmosphereOverlay) return;
        const atm = HISTORY_DATA.atmosphere[sceneId];
        if (!atm) return;

        this.atmosphereOverlay.classList.remove('active');

        // 随机选取一条氛围文本
        const ambient = atm.ambient[Math.floor(Math.random() * atm.ambient.length)];
        this.atmosphereOverlay.textContent = ambient;

        setTimeout(() => {
            this.atmosphereOverlay.classList.add('active');
        }, 3000);

        // 一段时间后切换到声音描述
        setTimeout(() => {
            const sound = atm.sounds[Math.floor(Math.random() * atm.sounds.length)];
            this.atmosphereOverlay.textContent = '【' + sound + '】';
        }, 10000);
    },

    hideAtmosphere() {
        if (this.atmosphereOverlay) this.atmosphereOverlay.classList.remove('active');
    },

    // ============================================
    // 史料时间线面板
    // ============================================
    showTimeline() {
        const panel = document.getElementById('timeline-panel');
        if (!panel) return;
        if (panel.classList.contains('active')) {
            this.hideTimeline();
            return;
        }

        const list = document.getElementById('timeline-list');
        list.innerHTML = '';

        const phaseNames = {
            prelude: '前奏', war: '战争', crisis: '危机',
            decision: '抉择', flee: '出逃', disaster: '灾难',
            fall: '陷落', treaty: '签约', death: '驾崩', aftermath: '余波'
        };

        HISTORY_DATA.timeline.forEach((item, idx) => {
            const entry = document.createElement('div');
            entry.className = 'timeline-entry phase-' + (item.phase || 'default');
            const isLast = idx === HISTORY_DATA.timeline.length - 1;
            entry.innerHTML = `
                <div class="timeline-dot-col">
                    <div class="timeline-big-dot"></div>
                    ${isLast ? '' : '<div class="timeline-line"></div>'}
                </div>
                <div class="timeline-content">
                    <div class="timeline-date">
                        ${item.date}
                        <span class="timeline-phase-label">${phaseNames[item.phase] || ''}</span>
                    </div>
                    <div class="timeline-event-text">
                        ${item.event}
                        ${item.verified ? '<span class="timeline-verified">已核实</span>' : ''}
                    </div>
                </div>
            `;
            list.appendChild(entry);
        });

        panel.classList.add('active');
    },

    hideTimeline() {
        const panel = document.getElementById('timeline-panel');
        if (panel) panel.classList.remove('active');
    },

    showDialogue(npcId, onComplete) {
        // 同时查找朝廷NPC和工商士农NPC
        let npc = HISTORY_DATA.npcs[npcId];
        let isCommoner = false;
        if (!npc) {
            npc = HISTORY_DATA.commoners ? HISTORY_DATA.commoners[npcId] : null;
            isCommoner = true;
        }
        if (!npc || !this.dialoguePanel) return;

        const avatarEl = this.dialoguePanel.querySelector('.dialogue-avatar');
        const nameEl = this.dialoguePanel.querySelector('.dialogue-name');
        const titleEl = this.dialoguePanel.querySelector('.dialogue-title');
        const contentEl = this.dialoguePanel.querySelector('.dialogue-content');
        const sourceEl = this.dialoguePanel.querySelector('.dialogue-source');
        const optionsEl = this.dialoguePanel.querySelector('.dialogue-options');

        avatarEl.textContent = npc.avatar;
        avatarEl.style.borderColor = npc.color;
        nameEl.innerHTML = npc.name + (isCommoner ? ' <span class="class-badge ' + npc.class + '">' + npc.class + '</span>' : '');
        titleEl.textContent = npc.title;

        // 显示问候语
        contentEl.textContent = npc.dialogues.greeting;
        sourceEl.style.display = 'none';
        optionsEl.innerHTML = '';

        this.dialoguePanel.classList.add('active');

        // 构建话题选项
        const topics = npc.dialogues.topics;
        const shownTopics = [];

        function showTopicOptions() {
            optionsEl.innerHTML = '';

            Object.keys(topics).forEach(topicId => {
                const topic = topics[topicId];
                if (shownTopics.includes(topicId)) return;

                const btn = document.createElement('button');
                btn.className = 'dialogue-option';
                btn.textContent = getTopicLabel(topicId);
                btn.onclick = () => {
                    shownTopics.push(topicId);
                    GameState.recordDialogue(npcId, topicId);

                    contentEl.textContent = topic.text;
                    sourceEl.textContent = '出处：' + topic.source;
                    sourceEl.style.display = 'block';

                    // 显示解锁的话题
                    if (topic.unlocks) {
                        topic.unlocks.forEach(unlockId => {
                            if (!GameState.knowledgeUnlocked.includes(unlockId)) {
                                GameState.knowledgeUnlocked.push(unlockId);
                            }
                        });
                    }

                    // 延迟后显示更多选项或关闭
                    setTimeout(() => {
                        const remainingTopics = Object.keys(topics).filter(t => !shownTopics.includes(t));
                        if (remainingTopics.length > 0) {
                            showTopicOptions();
                        } else {
                            optionsEl.innerHTML = '';
                            const closeBtn = document.createElement('button');
                            closeBtn.className = 'dialogue-option';
                            closeBtn.textContent = '【结束对话】';
                            closeBtn.onclick = () => {
                                UIManager.hideDialogue();
                                if (onComplete) onComplete();
                            };
                            optionsEl.appendChild(closeBtn);
                        }
                    }, 500);
                };
                optionsEl.appendChild(btn);
            });

            if (optionsEl.children.length === 0) {
                const closeBtn = document.createElement('button');
                closeBtn.className = 'dialogue-option';
                closeBtn.textContent = '【结束对话】';
                closeBtn.onclick = () => {
                    UIManager.hideDialogue();
                    if (onComplete) onComplete();
                };
                optionsEl.appendChild(closeBtn);
            }
        }

        showTopicOptions();
    },

    hideDialogue() {
        if (this.dialoguePanel) {
            this.dialoguePanel.classList.remove('active');
        }
    },

    showDecision(decisionId, onComplete) {
        const decision = HISTORY_DATA.decisions[decisionId];
        if (!decision || !this.decisionPanel) return;

        const titleEl = this.decisionPanel.querySelector('.decision-title');
        const contextEl = this.decisionPanel.querySelector('.decision-context');
        const optionsEl = this.decisionPanel.querySelector('.decision-options');

        titleEl.textContent = decision.title;
        contextEl.textContent = decision.context;
        optionsEl.innerHTML = '';

        this.decisionPanel.classList.add('active');

        decision.options.forEach(option => {
            const btn = document.createElement('button');
            btn.className = 'decision-option';
            btn.textContent = option.text;
            btn.onclick = () => {
                GameState.recordDecision(decisionId, option.id, option.historicalAccuracy);
                this.decisionPanel.classList.remove('active');

                // 显示反馈
                this.showFeedback(option.feedback, option.narratorComment, () => {
                    // 根据当前决策ID解锁对应场景
                    const targetSceneId = DECISION_SCENE_MAP[decisionId];
                    if (targetSceneId && HISTORY_DATA.scenes.find(s => s.id === targetSceneId)) {
                        GameState.unlockScene(targetSceneId);
                    }

                    // 处理选项级别的特殊解锁（结局等）
                    if (option.unlocks) {
                        option.unlocks.forEach(unlockId => {
                            if (unlockId.startsWith('ending_') || unlockId.startsWith('alt_history_')) {
                                setTimeout(() => this.showEnding(unlockId), 500);
                            } else if (HISTORY_DATA.scenes.find(s => s.id === unlockId)) {
                                GameState.unlockScene(unlockId);
                            }
                        });
                    }
                    if (onComplete) onComplete(option);
                });
            };
            optionsEl.appendChild(btn);
        });
    },

    showFeedback(feedbackText, narratorComment, onComplete) {
        if (!this.feedbackPanel) {
            if (onComplete) onComplete();
            return;
        }

        const textEl = this.feedbackPanel.querySelector('.feedback-text');
        textEl.textContent = feedbackText;
        this.feedbackPanel.classList.add('active');

        // 旁白评论
        if (narratorComment && GameState.narratorEnabled) {
            setTimeout(() => {
                this.showNarrator(narratorComment, 4000);
            }, 500);
        }

        // 自动关闭
        setTimeout(() => {
            this.feedbackPanel.classList.remove('active');
            if (onComplete) onComplete();
        }, 4000);
    },

    showEnding(endingId) {
        const ending = HISTORY_DATA.endings[endingId];
        if (!ending || !this.endingPanel) return;

        GameState.gameEnded = true;

        const titleEl = this.endingPanel.querySelector('.ending-title');
        const subtitleEl = this.endingPanel.querySelector('.ending-subtitle');
        const contentEl = this.endingPanel.querySelector('.ending-content');
        const noteEl = this.endingPanel.querySelector('.ending-note');

        titleEl.textContent = ending.title;
        subtitleEl.textContent = ending.description;
        contentEl.textContent = ending.content;
        noteEl.textContent = ending.historicalNote;

        this.endingPanel.classList.add('active');
    },

    hideEnding() {
        if (this.endingPanel) {
            this.endingPanel.classList.remove('active');
        }
    },

    showMinimap(currentSceneId, onTeleport) {
        if (!this.minimapPanel) return;

        const locationsEl = this.minimapPanel.querySelector('.minimap-locations');
        locationsEl.innerHTML = '';

        HISTORY_DATA.scenes.forEach(scene => {
            const div = document.createElement('div');
            div.className = 'minimap-location';
            if (scene.id === currentSceneId) {
                div.classList.add('current');
            }
            if (!GameState.unlockedScenes.includes(scene.id)) {
                div.classList.add('locked');
            }
            div.textContent = (scene.id === currentSceneId ? '● ' : '') + scene.name;

            if (GameState.unlockedScenes.includes(scene.id) && scene.id !== currentSceneId) {
                div.onclick = () => {
                    this.hideMinimap();
                    if (onTeleport) onTeleport(scene.id);
                };
            }
            locationsEl.appendChild(div);
        });

        this.minimapPanel.classList.add('active');
    },

    hideMinimap() {
        if (this.minimapPanel) {
            this.minimapPanel.classList.remove('active');
        }
    },

    showHistoryLog() {
        if (!this.historyLogPanel) return;

        const container = this.historyLogPanel;
        container.innerHTML = '<div class="history-log-title">史实记录</div>';

        if (GameState.decisionsMade.length === 0) {
            const entry = document.createElement('div');
            entry.className = 'history-log-entry';
            entry.textContent = '暂无记录';
            container.appendChild(entry);
        } else {
            GameState.decisionsMade.forEach(decision => {
                const decisionData = HISTORY_DATA.decisions[decision.decisionId];
                const option = decisionData.options.find(o => o.id === decision.optionId);

                const entry = document.createElement('div');
                entry.className = 'history-log-entry ' + (decision.isAccurate ? 'accurate' : 'inaccurate');
                entry.innerHTML = `
                    <strong>${decisionData.title}</strong><br>
                    你的选择：${option ? option.text : '未知'}<br>
                    <small>${decision.isAccurate ? '✓ 符合史实' : '✗ 偏离史实'}</small>
                `;
                container.appendChild(entry);
            });
        }

        container.classList.add('active');
    },

    hideHistoryLog() {
        if (this.historyLogPanel) {
            this.historyLogPanel.classList.remove('active');
        }
    },

    showInteractionHint(text) {
        if (!this.interactionHint) return;
        this.interactionHint.textContent = text;
        this.interactionHint.classList.add('active');
    },

    hideInteractionHint() {
        if (!this.interactionHint) return;
        this.interactionHint.classList.remove('active');
    }
};

function getTopicLabel(topicId) {
    const labels = {
        defense: '询问防务',
        treaty: '询问和谈',
        opinion: '询问对策',
        battle: '询问战况',
        rematch: '询问再战',
        reality: '询问实情',
        situation: '询问局势',
        advice: '询问对策',
        power: '询问朝局',
        child: '询问皇子',
        worry: '询问担忧',
        future: '询问将来',
        fear: '询问恐惧',
        dream: '询问梦境'
    };
    return labels[topicId] || topicId;
}

// ============================================
// Phaser 场景：启动场景
// ============================================
class BootScene extends Phaser.Scene {
    constructor() {
        super({ key: 'BootScene' });
    }

    create() {
        // 生成程序纹理
        this.generateTextures();

        // 初始化 UI
        UIManager.init();

        // 初始化音频引擎
        AmbientAudio.init();

        // 检查是否触摸设备
        const isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
        if (isTouch) {
            document.getElementById('virtual-joystick').classList.add('active');
        }

        // 显示开始菜单
        this.showMainMenu();
    }

    generateTextures() {
        // 玩家纹理
        const playerGfx = this.make.graphics({ x: 0, y: 0, add: false });
        playerGfx.fillStyle(0xFFD700);
        playerGfx.fillCircle(16, 16, 14);
        playerGfx.lineStyle(2, 0x8B4513);
        playerGfx.strokeCircle(16, 16, 14);
        playerGfx.generateTexture('player', 32, 32);

        // NPC纹理
        Object.values(HISTORY_DATA.npcs).forEach(npc => {
            const gfx = this.make.graphics({ x: 0, y: 0, add: false });
            const color = parseInt(npc.color.replace('#', '0x'));
            gfx.fillStyle(color);
            gfx.fillCircle(16, 16, 14);
            gfx.lineStyle(2, 0xFFFFFF);
            gfx.strokeCircle(16, 16, 14);
            gfx.generateTexture('npc_' + npc.id, 32, 32);
        });

        // 工商士农NPC纹理（方形区分于圆形的朝廷NPC）
        if (HISTORY_DATA.commoners) {
            Object.values(HISTORY_DATA.commoners).forEach(npc => {
                const gfx = this.make.graphics({ x: 0, y: 0, add: false });
                const color = parseInt(npc.color.replace('#', '0x'));
                gfx.fillStyle(color);
                gfx.fillRoundedRect(2, 2, 28, 28, 6);
                gfx.lineStyle(2, 0xAAAAAA);
                gfx.strokeRoundedRect(2, 2, 28, 28, 6);
                gfx.generateTexture('npc_' + npc.id, 32, 32);
            });
        }

        // 墙壁纹理
        const wallGfx = this.make.graphics({ x: 0, y: 0, add: false });
        wallGfx.fillStyle(0x5a4a3a);
        wallGfx.fillRect(0, 0, 32, 32);
        wallGfx.lineStyle(1, 0x3a2a1a);
        wallGfx.strokeRect(0, 0, 32, 32);
        wallGfx.generateTexture('wall', 32, 32);

        // 地板纹理
        const floorGfx = this.make.graphics({ x: 0, y: 0, add: false });
        floorGfx.fillStyle(0x4a3525);
        floorGfx.fillRect(0, 0, 32, 32);
        floorGfx.lineStyle(1, 0x3a2515);
        floorGfx.strokeRect(0, 0, 32, 32);
        floorGfx.generateTexture('floor', 32, 32);

        // 出口纹理
        const exitGfx = this.make.graphics({ x: 0, y: 0, add: false });
        exitGfx.fillStyle(0x228B22, 0.6);
        exitGfx.fillRect(0, 0, 32, 32);
        exitGfx.lineStyle(2, 0x90EE90);
        exitGfx.strokeRect(0, 0, 32, 32);
        exitGfx.generateTexture('exit', 32, 32);

        // 装饰纹理
        const decoGfx = this.make.graphics({ x: 0, y: 0, add: false });
        decoGfx.fillStyle(0x8B4513);
        decoGfx.fillRect(4, 4, 24, 24);
        decoGfx.lineStyle(1, 0xD4AF37);
        decoGfx.strokeRect(4, 4, 24, 24);
        decoGfx.generateTexture('decoration', 32, 32);
    }

    showMainMenu() {
        const menuScreen = document.getElementById('menu-screen');
        menuScreen.classList.remove('hidden');

        const startBtn = document.getElementById('start-btn');
        startBtn.onclick = () => {
            menuScreen.classList.add('hidden');
            GameState.reset();
            GameState.gameStarted = true;
            this.scene.start('PlayScene', { sceneId: 'yangxindian', x: 400, y: 500 });
        };
    }
}

// ============================================
// Phaser 场景：主游戏场景
// ============================================
class PlayScene extends Phaser.Scene {
    constructor() {
        super({ key: 'PlayScene' });
    }

    init(data) {
        this.sceneId = data.sceneId || 'yangxindian';
        this.startX = data.x || 400;
        this.startY = data.y || 300;
        this.sceneData = HISTORY_DATA.scenes.find(s => s.id === this.sceneId);
        this.isPaused = false;
        this.nearbyNPC = null;
        this.nearbyExit = null;
    }

    create() {
        if (!this.sceneData) {
            console.error('Scene not found:', this.sceneId);
            return;
        }

        GameState.currentSceneId = this.sceneId;
        GameState.visitScene(this.sceneId);

        // 更新 UI
        this.updateTopBar();

        // 创建场景
        this.createWorld();

        // 创建玩家
        this.createPlayer();

        // 创建 NPC
        this.createNPCs();

        // 创建出口
        this.createExits();

        // 创建装饰
        this.createDecorations();

        // 创建场景标题浮动文字效果
        this.createSceneTitle();

        // 创建实时局势文字条
        this.createStatusBar();

        // 设置输入
        this.setupInput();

        // 设置摄像机
        this.cameras.main.startFollow(this.player, true, 0.1, 0.1);
        this.cameras.main.setZoom(1.2);

        // 场景进入旁白
        if (GameState.narratorEnabled) {
            const entranceLines = HISTORY_DATA.narratorLines.entrance;
            const randomLine = entranceLines[Math.floor(Math.random() * entranceLines.length)];
            UIManager.showNarrator(this.sceneData.description, 4000);

            if (GameState.visitedScenes.length === 1) {
                setTimeout(() => {
                    UIManager.showNarrator(randomLine, 5000);
                }, 2000);
            }
        }

        // 检查决策触发
        this.checkDecisionTrigger();

        // 场景氛围系统（延迟触发，不干扰开场旁白）
        this.time.delayedCall(8000, () => {
            UIManager.showAtmosphere(this.sceneId);
        });

        // 场景背景音效
        if (AmbientAudio.initialized) {
            AmbientAudio.resume();
            AmbientAudio.playScene(this.sceneId);
        }

        // 闲置检测
        this.idleEvent = this.time.addEvent({
            delay: 15000,
            callback: this.onIdle,
            callbackScope: this,
            loop: true
        });
    }

    update() {
        if (this.isPaused) return;

        this.handlePlayerMovement();
        this.checkProximity();
        this.updateVirtualJoystick();
    }

    createWorld() {
        // 背景
        const bgColor = parseInt(this.sceneData.bgColor.replace('#', '0x'));
        this.cameras.main.setBackgroundColor(bgColor);

        // 地板区域（简单填充）
        const floorGfx = this.add.graphics();
        const floorColor = parseInt(this.sceneData.floorColor.replace('#', '0x'));
        floorGfx.fillStyle(floorColor, 1);
        floorGfx.fillRect(-500, -500, 2000, 2000);

        // 墙壁
        this.walls = this.physics.add.staticGroup();
        if (this.sceneData.walls) {
            this.sceneData.walls.forEach(wall => {
                const wallSprite = this.walls.create(wall.x + wall.w / 2, wall.y + wall.h / 2, 'wall');
                wallSprite.setDisplaySize(wall.w, wall.h);
                wallSprite.setAlpha(0.9);
                wallSprite.body.setSize(wall.w, wall.h);
            });
        }

        // 世界边界
        this.physics.world.setBounds(0, 0, 1200, 800);
    }

    createPlayer() {
        this.player = this.physics.add.sprite(this.startX, this.startY, 'player');
        this.player.setCollideWorldBounds(true);
        this.player.setDepth(10);

        // 与墙壁碰撞
        this.physics.add.collider(this.player, this.walls);

        // 玩家光源效果
        const lightGfx = this.add.graphics();
        lightGfx.fillStyle(0xFFD700, 0.1);
        lightGfx.fillCircle(0, 0, 80);
        lightGfx.setDepth(9);
        this.playerLight = lightGfx;
    }

    createNPCs() {
        this.npcSprites = {};
        this.npcGroup = this.physics.add.staticGroup();

        // NPC位置池
        const positions = [
            { x: 300, y: 300 }, { x: 500, y: 250 }, { x: 400, y: 400 },
            { x: 200, y: 400 }, { x: 600, y: 350 }, { x: 150, y: 250 },
            { x: 650, y: 450 }, { x: 350, y: 500 }, { x: 700, y: 300 }
        ];
        let posIndex = 0;

        // 朝廷NPC
        if (this.sceneData.npcs) {
            this.sceneData.npcs.forEach((npcId) => {
                const npcData = HISTORY_DATA.npcs[npcId];
                if (!npcData) return;

                const pos = positions[posIndex % positions.length];
                posIndex++;

                const npcSprite = this.npcGroup.create(pos.x, pos.y, 'npc_' + npcId);
                npcSprite.setDepth(10);
                npcSprite.setInteractive();

                const label = this.add.text(pos.x, pos.y - 25, npcData.name, {
                    fontSize: '12px', color: '#d4af37', fontFamily: 'GameFont'
                }).setOrigin(0.5).setDepth(11);

                npcSprite.on('pointerdown', () => this.interactWithNPC(npcId));
                this.npcSprites[npcId] = { sprite: npcSprite, label: label, data: npcData };
            });
        }

        // 工商士农NPC（方形标识，灰色名称）
        if (this.sceneData.commoners && HISTORY_DATA.commoners) {
            this.sceneData.commoners.forEach((npcId) => {
                const npcData = HISTORY_DATA.commoners[npcId];
                if (!npcData) return;

                const pos = positions[posIndex % positions.length];
                posIndex++;

                const npcSprite = this.npcGroup.create(pos.x, pos.y, 'npc_' + npcId);
                npcSprite.setDepth(10);
                npcSprite.setInteractive();
                npcSprite.setAlpha(0.85);

                const classLabel = '[' + npcData.class + '] ' + npcData.name;
                const label = this.add.text(pos.x, pos.y - 25, classLabel, {
                    fontSize: '11px', color: '#a09080', fontFamily: 'GameFont'
                }).setOrigin(0.5).setDepth(11);

                npcSprite.on('pointerdown', () => this.interactWithNPC(npcId));
                this.npcSprites[npcId] = { sprite: npcSprite, label: label, data: npcData };
            });
        }
    }

    createExits() {
        this.exitGroup = this.physics.add.staticGroup();
        this.exitData = [];

        if (this.sceneData.exits) {
            this.sceneData.exits.forEach(exit => {
                const exitSprite = this.exitGroup.create(
                    exit.x + exit.w / 2,
                    exit.y + exit.h / 2,
                    'exit'
                );
                exitSprite.setDisplaySize(exit.w, exit.h);
                exitSprite.setAlpha(0.5);
                exitSprite.setDepth(5);

                // 出口标签
                const label = this.add.text(exit.x + exit.w / 2, exit.y + exit.h / 2 - 15, exit.label, {
                    fontSize: '11px',
                    color: '#90EE90',
                    fontFamily: 'GameFont'
                }).setOrigin(0.5).setDepth(6);

                this.exitData.push({ ...exit, sprite: exitSprite, label: label });
            });
        }
    }

    createDecorations() {
        if (this.sceneData.decorations) {
            this.sceneData.decorations.forEach(deco => {
                const decoSprite = this.add.sprite(deco.x, deco.y, 'decoration');
                decoSprite.setDepth(8);
                decoSprite.setAlpha(0.7);

                const label = this.add.text(deco.x, deco.y - 20, deco.label, {
                    fontSize: '11px',
                    color: '#a09080',
                    fontFamily: 'GameFont'
                }).setOrigin(0.5).setDepth(9);
            });
        }
    }

    // ============================================
    // 场景标题浮动文字效果
    // ============================================
    createSceneTitle() {
        const cx = this.cameras.main.width / 2;
        const cy = this.cameras.main.height / 3;

        // 场景名大字
        const titleText = this.add.text(cx, cy, this.sceneData.name, {
            fontSize: '48px',
            color: '#d4af37',
            fontFamily: 'GameFont, SimSun, serif',
            fontStyle: 'bold',
            stroke: '#2a1a0a',
            strokeThickness: 6,
            shadow: { offsetX: 3, offsetY: 3, color: '#1a0a00', blur: 8, fill: true }
        }).setOrigin(0.5).setDepth(100).setAlpha(0);

        // 副标题
        const subText = this.add.text(cx, cy + 55, this.sceneData.description, {
            fontSize: '16px',
            color: '#c8b8a8',
            fontFamily: 'GameFont, SimSun, serif',
            fontStyle: 'italic',
            shadow: { offsetX: 1, offsetY: 1, color: '#000', blur: 4, fill: true }
        }).setOrigin(0.5).setDepth(100).setAlpha(0);

        // 淡入动画
        this.tweens.add({ targets: titleText, alpha: 1, duration: 800, ease: 'Power2' });
        this.tweens.add({ targets: subText, alpha: 1, duration: 800, delay: 200, ease: 'Power2' });

        // 延迟后淡出
        this.time.delayedCall(3000, () => {
            this.tweens.add({ targets: [titleText, subText], alpha: 0, duration: 1200, ease: 'Power2', onComplete: () => {
                titleText.destroy();
                subText.destroy();
            }});
        });
    }

    // ============================================
    // 实时局势文字条（画面上方固定位置）
    // ============================================
    createStatusBar() {
        const cx = this.cameras.main.width / 2;
        const y = 60;

        const statusTexts = {
            yangxindian: '深夜，御案前——八百里加急，八里桥大败',
            gongmen: '午门外，秋风萧瑟——远处隆隆炮声，联军逼近',
            yizhan: '黎明前，驿站——銮驾已备，仓皇北狩在即',
            bishushanzhuang: '塞外，避暑山庄——龙体抱恙，国事日非',
            yanbozhishuang: '烟波致爽殿，病榻之上——割地赔款，丧权辱国'
        };

        const text = statusTexts[this.sceneId] || this.sceneData.description;

        this.statusBarText = this.add.text(cx, y, text, {
            fontSize: '13px',
            color: '#b0a090',
            fontFamily: 'GameFont, SimSun, serif',
            align: 'center',
            wordWrap: { width: 600 }
        }).setOrigin(0.5).setDepth(100).setAlpha(0);

        // 缓缓淡入
        this.tweens.add({ targets: this.statusBarText, alpha: 0.85, duration: 2000, delay: 1500, ease: 'Power2' });
    }

    setupInput() {
        // 键盘输入
        this.cursors = this.input.keyboard.createCursorKeys();
        this.wasd = this.input.keyboard.addKeys({
            up: Phaser.Input.Keyboard.KeyCodes.W,
            down: Phaser.Input.Keyboard.KeyCodes.S,
            left: Phaser.Input.Keyboard.KeyCodes.A,
            right: Phaser.Input.Keyboard.KeyCodes.D
        });

        // 交互键
        this.input.keyboard.on('keydown-SPACE', () => {
            if (this.nearbyNPC) {
                this.interactWithNPC(this.nearbyNPC);
            } else if (this.nearbyExit) {
                this.useExit(this.nearbyExit);
            }
        });

        this.input.keyboard.on('keydown-E', () => {
            if (this.nearbyNPC) {
                this.interactWithNPC(this.nearbyNPC);
            }
        });

        // M键 - 小地图
        this.input.keyboard.on('keydown-M', () => {
            UIManager.hideGeopolitics();
            UIManager.hideHistoryLog();
            UIManager.hideTimeline();
            if (UIManager.minimapPanel.classList.contains('active')) {
                UIManager.hideMinimap();
            } else {
                UIManager.showMinimap(this.sceneId, (sceneId) => {
                    this.transitionToScene(sceneId);
                });
            }
        });

        // H键 - 历史日志
        this.input.keyboard.on('keydown-H', () => {
            UIManager.hideMinimap();
            UIManager.hideGeopolitics();
            UIManager.hideTimeline();
            if (UIManager.historyLogPanel.classList.contains('active')) {
                UIManager.hideHistoryLog();
            } else {
                UIManager.showHistoryLog();
            }
        });

        // L键 - 史料时间线
        this.input.keyboard.on('keydown-L', () => {
            UIManager.hideMinimap();
            UIManager.hideGeopolitics();
            UIManager.hideHistoryLog();
            UIManager.showTimeline();
        });

        // G键 - 国力与国际局势
        this.input.keyboard.on('keydown-G', () => {
            UIManager.hideMinimap();
            UIManager.hideHistoryLog();
            UIManager.hideTimeline();
            UIManager.showGeopolitics();
        });

        // T键 - TTS旁白配音开关
        this.input.keyboard.on('keydown-T', () => {
            const enabled = TTSNarrator.toggle();
            const ttsBtn = document.getElementById('btn-tts');
            if (ttsBtn) ttsBtn.textContent = enabled ? '🔊' : '🔇';
            UIManager.showNarrator(enabled ? '旁白配音已开启' : '旁白配音已关闭', 2000);
        });

        // X键 - 场景音效开关
        this.input.keyboard.on('keydown-X', () => {
            const enabled = AmbientAudio.toggle();
            const audioBtn = document.getElementById('btn-audio');
            if (audioBtn) {
                audioBtn.textContent = enabled ? '🎵' : '🔇';
                audioBtn.classList.toggle('muted', !enabled);
            }
            if (enabled) {
                AmbientAudio.playScene(this.sceneId);
            }
        });

        // 虚拟摇杆
        this.setupVirtualJoystick();
    }

    setupVirtualJoystick() {
        const joystickEl = document.getElementById('virtual-joystick');
        if (!joystickEl || !joystickEl.classList.contains('active')) return;

        const base = joystickEl.querySelector('.joystick-base');
        const knob = joystickEl.querySelector('.joystick-knob');
        const rect = joystickEl.getBoundingClientRect();
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        const maxDist = 35;

        this.joystickVector = { x: 0, y: 0 };
        this.joystickActive = false;

        const handleStart = (e) => {
            e.preventDefault();
            this.joystickActive = true;
        };

        const handleMove = (e) => {
            if (!this.joystickActive) return;
            e.preventDefault();

            const touch = e.touches ? e.touches[0] : e;
            const rect = joystickEl.getBoundingClientRect();
            const dx = touch.clientX - rect.left - centerX;
            const dy = touch.clientY - rect.top - centerY;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const angle = Math.atan2(dy, dx);

            const clampedDist = Math.min(dist, maxDist);
            const knobX = Math.cos(angle) * clampedDist + centerX - 20;
            const knobY = Math.sin(angle) * clampedDist + centerY - 20;

            knob.style.left = knobX + 'px';
            knob.style.top = knobY + 'px';

            this.joystickVector.x = (Math.cos(angle) * clampedDist) / maxDist;
            this.joystickVector.y = (Math.sin(angle) * clampedDist) / maxDist;
        };

        const handleEnd = (e) => {
            e.preventDefault();
            this.joystickActive = false;
            this.joystickVector = { x: 0, y: 0 };
            knob.style.left = '30px';
            knob.style.top = '30px';
        };

        joystickEl.addEventListener('touchstart', handleStart, { passive: false });
        joystickEl.addEventListener('touchmove', handleMove, { passive: false });
        joystickEl.addEventListener('touchend', handleEnd, { passive: false });
    }

    handlePlayerMovement() {
        const speed = 160;
        let vx = 0;
        let vy = 0;

        // 键盘输入
        if (this.cursors.left.isDown || this.wasd.left.isDown) vx = -1;
        if (this.cursors.right.isDown || this.wasd.right.isDown) vx = 1;
        if (this.cursors.up.isDown || this.wasd.up.isDown) vy = -1;
        if (this.cursors.down.isDown || this.wasd.down.isDown) vy = 1;

        // 虚拟摇杆输入
        if (this.joystickActive && this.joystickVector) {
            if (Math.abs(this.joystickVector.x) > 0.1) vx = this.joystickVector.x;
            if (Math.abs(this.joystickVector.y) > 0.1) vy = this.joystickVector.y;
        }

        // 归一化对角线移动
        if (vx !== 0 && vy !== 0) {
            const factor = 1 / Math.sqrt(2);
            vx *= factor;
            vy *= factor;
        }

        this.player.setVelocity(vx * speed, vy * speed);

        // 更新光源位置
        if (this.playerLight) {
            this.playerLight.x = this.player.x;
            this.playerLight.y = this.player.y;
        }

        // 闲置计时重置
        if (vx !== 0 || vy !== 0) {
            GameState.idleTime = 0;
        }
    }

    updateVirtualJoystick() {
        // 摇杆更新在 handlePlayerMovement 中处理
    }

    checkProximity() {
        const interactionDistance = 60;
        let foundNPC = null;
        let foundExit = null;

        // 检查 NPC  proximity
        Object.keys(this.npcSprites).forEach(npcId => {
            const npc = this.npcSprites[npcId];
            const dist = Phaser.Math.Distance.Between(
                this.player.x, this.player.y,
                npc.sprite.x, npc.sprite.y
            );

            if (dist < interactionDistance) {
                foundNPC = npcId;
            }
        });

        // 检查出口 proximity
        this.exitData.forEach(exit => {
            const dist = Phaser.Math.Distance.Between(
                this.player.x, this.player.y,
                exit.sprite.x, exit.sprite.y
            );

            if (dist < interactionDistance) {
                foundExit = exit;
            }
        });

        this.nearbyNPC = foundNPC;
        this.nearbyExit = foundExit;

        // 更新交互提示
        if (foundNPC) {
            let npcData = HISTORY_DATA.npcs[foundNPC];
            if (!npcData && HISTORY_DATA.commoners) {
                npcData = HISTORY_DATA.commoners[foundNPC];
            }
            if (npcData) {
                UIManager.showInteractionHint(`按空格键与 ${npcData.name} 交谈`);
            }
        } else if (foundExit) {
            UIManager.showInteractionHint(`按空格键${foundExit.label}`);
        } else {
            UIManager.hideInteractionHint();
        }
    }

    interactWithNPC(npcId) {
        this.isPaused = true;
        this.player.setVelocity(0, 0);

        UIManager.showDialogue(npcId, () => {
            this.isPaused = false;
            // 检查决策触发
            this.checkDecisionTrigger();
        });
    }

    useExit(exit) {
        const targetScene = HISTORY_DATA.scenes.find(s => s.id === exit.target);
        if (!targetScene) return;

        // 检查目标场景是否已解锁
        if (!GameState.unlockedScenes.includes(exit.target)) {
            // 额外检查：如果目标场景有决策触发器，且该决策的前置条件（当前场景的决策）已完成
            // 则也允许通行（向后兼容）
            const canPass = GameState.decisionsMade.some(d => {
                const mappedScene = DECISION_SCENE_MAP[d.decisionId];
                return mappedScene === exit.target;
            });

            if (!canPass) {
                UIManager.showNarrator('此处尚未解锁。', 2000);
                return;
            }
            // 如果决策已完成但场景未在 unlockedScenes 中，补录
            GameState.unlockScene(exit.target);
        }

        // 计算进入新场景的位置（从对应出口反向进入）
        let targetX = 400;
        let targetY = 300;

        // 找到目标场景中指向当前场景的出口，从其反方向进入
        if (targetScene && targetScene.exits) {
            const returnExit = targetScene.exits.find(e => e.target === this.sceneId);
            if (returnExit) {
                targetX = returnExit.x + returnExit.w / 2;
                targetY = returnExit.y + returnExit.h / 2;

                // 稍微偏移，避免卡在出口里
                if (targetY < 100) targetY += 60;
                else if (targetY > 500) targetY -= 60;
                if (targetX < 100) targetX += 60;
                else if (targetX > 700) targetX -= 60;
            }
        }

        this.transitionToScene(exit.target, targetX, targetY);
    }

    transitionToScene(sceneId, x, y) {
        this.isPaused = true;

        this.cameras.main.fadeOut(500, 0, 0, 0);
        this.cameras.main.once(Phaser.Cameras.Scene2D.Events.FADE_OUT_COMPLETE, () => {
            this.scene.start('PlayScene', {
                sceneId: sceneId,
                x: x || 400,
                y: y || 300
            });
        });
    }

    checkDecisionTrigger() {
        if (this.sceneData.decisionTrigger && !GameState.gameEnded) {
            const decisionId = this.sceneData.decisionTrigger;
            const alreadyDecided = GameState.decisionsMade.some(d => d.decisionId === decisionId);

            if (!alreadyDecided) {
                // 延迟显示决策，给玩家时间观察场景
                this.time.delayedCall(1000, () => {
                    this.isPaused = true;
                    this.player.setVelocity(0, 0);

                    UIManager.showDecision(decisionId, (option) => {
                        this.isPaused = false;

                        // 检查此决策是否解锁了新场景，提示玩家
                        const mappedScene = DECISION_SCENE_MAP[decisionId];
                        const optionUnlocksScene = option.unlocks && option.unlocks.some(id =>
                            HISTORY_DATA.scenes.find(s => s.id === id)
                        );
                        if ((mappedScene && HISTORY_DATA.scenes.find(s => s.id === mappedScene)) || optionUnlocksScene) {
                            UIManager.showNarrator('新的地点已解锁，可通过出口前往。', 3000);
                        }
                    });
                });
            }
        }
    }

    onIdle() {
        if (this.isPaused || !GameState.narratorEnabled) return;

        GameState.idleTime += 15;

        // 根据闲置时间触发不同旁白
        if (GameState.idleTime >= 30) {
            const idleLines = HISTORY_DATA.narratorLines.idle;
            const randomLine = idleLines[Math.floor(Math.random() * idleLines.length)];
            UIManager.showNarrator(randomLine, 4000);
            GameState.idleTime = 0;
        }
    }

    updateTopBar() {
        const sceneNameEl = document.getElementById('scene-name');
        const sceneDescEl = document.getElementById('scene-desc');

        if (sceneNameEl) sceneNameEl.textContent = this.sceneData.name;
        if (sceneDescEl) sceneDescEl.textContent = this.sceneData.description;

        // 更新顶部 HUD 日期
        const hudDate = document.getElementById('hud-date');
        const hudEnemy = document.getElementById('hud-enemy');
        if (hudDate) {
            const dates = {
                yangxindian: '咸丰十年 · 九月廿一 · 深夜',
                gongmen: '咸丰十年 · 九月廿二 · 黎明',
                yizhan: '咸丰十年 · 九月廿二 · 拂晓',
                bishushanzhuang: '咸丰十年 · 九月三十 · 午后',
                yanbozhishuang: '咸丰十年 · 十月初六 · 黄昏'
            };
            hudDate.textContent = dates[this.sceneId] || '咸丰十年 · 九月';
        }
        if (hudEnemy) {
            const enemyStatus = {
                yangxindian: '逼近通州',
                gongmen: '兵临城下',
                yizhan: '已占北京',
                bishushanzhuang: '焚毁圆明园',
                yanbozhishuang: '条约已定'
            };
            hudEnemy.textContent = enemyStatus[this.sceneId] || '逼近北京';
        }
    }

    shutdown() {
        if (this.idleEvent) {
            this.idleEvent.remove();
        }
        UIManager.hideDialogue();
        UIManager.hideMinimap();
        UIManager.hideHistoryLog();
        UIManager.hideInteractionHint();
    }
}

// ============================================
// 游戏配置与启动
// ============================================
const config = {
    type: Phaser.AUTO,
    parent: 'game-container',
    width: window.innerWidth,
    height: window.innerHeight,
    backgroundColor: '#0a0a0a',
    physics: {
        default: 'arcade',
        arcade: {
            gravity: { y: 0 },
            debug: false
        }
    },
    scene: [BootScene, PlayScene],
    scale: {
        mode: Phaser.Scale.RESIZE,
        autoCenter: Phaser.Scale.CENTER_BOTH
    },
    render: {
        pixelArt: false,
        antialias: true
    }
};

// 全局游戏实例
let game;

function initGame() {
    if (game) {
        game.destroy(true);
    }
    game = new Phaser.Game(config);
}

// 页面加载完成后启动
window.addEventListener('load', initGame);

// 意向大小改变时调整
window.addEventListener('resize', () => {
    if (game) {
        game.scale.resize(window.innerWidth, window.innerHeight);
    }
});

// 防止页面滚动（移动端）
document.addEventListener('touchmove', function(e) {
    if (e.target.closest('#game-container')) {
        e.preventDefault();
    }
}, { passive: false });