// =================================================================================================
// SOCKET.IO REAL-TIME CONNECTION
// =================================================================================================
const socket = io('http://127.0.0.1:5000', {
    transports: ['polling', 'websocket'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 10
});

socket.on('connect', () => {
    console.log('✅ Connected to server via Socket.IO');
    socket.emit('request_gamestate');
});

socket.on('disconnect', () => {
    console.log('❌ Disconnected from server');
});

socket.on('gamestateupdate', (data) => {
    console.log('📡 Game state update received:', data);
    updateFromGameState(data);
});

socket.on('pointscored', (data) => {
    console.log('🎯 Point scored:', data);
    handleSensorInput(data);
});

socket.on('matchwon', (data) => {
    console.log('🏆 Match won:', data);
    displayWinner(data);
});

// =================================================================================================
// GAME VARIABLES
// =================================================================================================
let score1 = 0;
let score2 = 0;
let games1 = 0;
let games2 = 0;
let sets1 = 0;
let sets2 = 0;

let matchWon = false;
let winnerData = null;
let setsHistory = [];

let matchStartTime = Date.now();
let splashDismissed = false;
let winnerDismissTimeout = null;

let gameMode = null;            // 'basic', 'competition', 'lock', or null
let isScoreboardActive = false; // Track if scoreboard is ready for scoring

// Mode detection variables (legacy)
let pendingSensorEvents = [];   // Store recent sensor events
const DUAL_SENSOR_WINDOW = 800; // 800ms window to detect both sensors firing

const API_BASE = "http://127.0.0.1:5000";

// =================================================================================================
// SENSOR INPUT HANDLER WITH NEW FLOW
// =================================================================================================
function handleSensorInput(data) {
    const currentTime = Date.now();

    // STATE 1: Winner screen is showing - reset match and go to splash
    const winnerDisplay = document.getElementById('winnerDisplay');
    if (winnerDisplay && winnerDisplay.style.display === 'flex') {
        console.log('🏆 Winner screen visible - sensor input detected, resetting match and going to splash');
        clearWinnerTimeout();
        resetMatchAndGoToSplash();
        return;
    }

    // STATE 2: Splash screen is active - go directly to GAME MODE screen (NO SCORING)
    const splashScreen = document.getElementById('splashScreen');
    if (splashScreen && splashScreen.classList.contains('active')) {
        console.log('✨ Splash screen active - going to GAME MODE screen (NO SCORING)');
        dismissSplash(); // This now goes directly to game mode screen
        return;
    }

    // STATE 3: Mode selection screen (game mode screen) - handle addpoint/subtractpoint to select mode ONLY
    const modeScreen = document.getElementById('modeSelectionScreen');
    const modeScreenVisible = modeScreen && getComputedStyle(modeScreen).display === 'flex';

    if (modeScreenVisible) {
        console.log('🎮 Game mode screen active - handling sensor input (NO SCORING)');
        if (data.action === 'addpoint') {
            console.log('➕ addpoint detected on game mode screen - selecting BASIC mode (NO SCORING)');
            selectMode('basic');
        } else if (data.action === 'subtractpoint') {
            console.log('➖ subtractpoint detected on game mode screen - selecting COMPETITION mode (NO SCORING)');
            selectMode('competition');
        }
        return;
    }

    // STATE 4: Scoreboard is active - normal scoring
    if (isScoreboardActive && gameMode) {
        console.log('📊 Scoreboard active - processing point');
        // Visual feedback and toast notifications
        showClickFeedback(data.team);
        showToast(data.action, data.team, data.gamestate);
    }
}

// =================================================================================================
// MODE DETECTION LOGIC - LEGACY (unused)
// =================================================================================================
function detectAndSelectMode(data, currentTime) {
    // This function is now legacy - mode selection handled directly in handleSensorInput
    console.log('⚠️ Legacy mode detection called');
}

// =================================================================================================
// INITIALIZATION - AUTO SKIP TO GAME MODE SCREEN
// =================================================================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🏓 Padel Scoreboard Initialized - AUTO SKIPPING TO GAME MODE');

    // Show splash initially
    const splashScreen = document.getElementById('splashScreen');
    if (splashScreen) {
        splashScreen.classList.add('active');
        console.log('🎬 Splash screen displayed');
    }

    // AUTO-SKIP: Go directly to game mode screen after brief splash
    setTimeout(() => {
        console.log('🚀 Auto-skipping splash - going directly to game mode screen');
        dismissSplash();
    }, 1000); // 1 second splash for branding, then auto-advance

    setupLogo();

    // Start match duration timer (replaces clock)
    updateMatchDuration();
    setInterval(updateMatchDuration, 1000);

    setupClickableTeams();
    setupWinnerScreenClickDismiss();
});

// =================================================================================================
// SPLASH SCREEN - MODIFIED TO GO DIRECTLY TO GAME MODE
// =================================================================================================
function setupSplashScreen() {
    const splashScreen = document.getElementById('splashScreen');
    if (!splashScreen) return;

    const dismissSplashHandler = () => {
        dismissSplash();
    };
    splashScreen.addEventListener('click', dismissSplashHandler);
    splashScreen.addEventListener('touchstart', dismissSplashHandler);
}

function dismissSplash() {
    if (!splashDismissed) {
        splashDismissed = true;
        const splashScreen = document.getElementById('splashScreen');
        if (splashScreen) {
            splashScreen.classList.remove('active');
        }

        // Go DIRECTLY to game mode screen (no scoring until mode selected)
        setTimeout(() => {
            showModeSelection();
        }, 300);

        console.log('✨ Splash dismissed - showing GAME MODE screen (ready for addpoint/subtractpoint detection)');
    }
}

// =================================================================================================
// MODE SELECTION SCREEN (GAME MODE SCREEN)
// =================================================================================================
function showModeSelection() {
    const modeScreen = document.getElementById('modeSelectionScreen');
    if (modeScreen) {
        modeScreen.style.display = 'flex';
        // Force reflow
        modeScreen.offsetHeight;
        modeScreen.classList.add('active');

        // Reset pending sensor events when game mode screen appears
        pendingSensorEvents = [];
        console.log('🎮 GAME MODE screen shown - addpoint selects BASIC, subtractpoint selects COMPETITION (NO SCORING)');
    }
}

async function selectMode(mode) {
    console.log(`🎯 Mode selected: ${mode} - activating scoreboard`);

    // Set game mode locally
    gameMode = mode;

    // Send mode to backend
    try {
        const response = await fetch(`${API_BASE}/setgamemode`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
        const data = await response.json();
        if (data.success) {
            console.log(`✅ Game mode set to: ${mode} on backend`);
        } else {
            console.error('❌ Failed to set game mode:', data.error);
        }
    } catch (error) {
        console.error('❌ Error setting game mode:', error);
    }

    // Hide mode selection screen
    const modeScreen = document.getElementById('modeSelectionScreen');
    if (modeScreen) {
        modeScreen.classList.remove('active');
        setTimeout(() => {
            modeScreen.style.display = 'none';

            // NOW activate scoreboard for scoring (CRITICAL: only after mode selection)
            isScoreboardActive = true;
            matchStartTime = Date.now(); // reset timer on mode selection
            console.log('✅ ✅ SCOREBOARD NOW ACTIVE - points will count from here');
        }, 500);
    }
}

// =================================================================================================
// MATCH DURATION TIMER (REPLACES CLOCK)
// =================================================================================================
function updateMatchDuration() {
    const now = Date.now();
    const elapsed = now - matchStartTime;

    const totalSeconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    const formattedTime = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    const timeEl = document.getElementById('timeDisplay');
    if (timeEl) {
        timeEl.textContent = formattedTime;
    }
}

// =================================================================================================
// WINNER SCREEN MANAGEMENT
// =================================================================================================
function setupWinnerScreenClickDismiss() {
    const winnerDisplay = document.getElementById('winnerDisplay');
    if (winnerDisplay) {
        winnerDisplay.addEventListener('click', function(e) {
            // Don't close if clicking on buttons
            if (e.target.closest('.action-button')) {
                return;
            }
            // Only close if the winner screen is actually visible
            if (winnerDisplay.style.display === 'flex') {
                console.log('👆 Winner screen clicked - resetting match and going to splash');
                clearWinnerTimeout();
                resetMatchAndGoToSplash();
            }
        });
        console.log('✅ Winner screen click-to-dismiss enabled');
    }
}

function clearWinnerTimeout() {
    if (winnerDismissTimeout) {
        clearTimeout(winnerDismissTimeout);
        winnerDismissTimeout = null;
    }
}

async function resetMatchAndGoToSplash() {
    console.log('🔄 Resetting match, mode, and going to splash...');

    // 1. Reset match on backend
    try {
        const resetResponse = await fetch(`${API_BASE}/resetmatch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const resetData = await resetResponse.json();
        if (resetData.success) {
            console.log('✅ Match reset successfully on backend');
        } else {
            console.error('❌ Failed to reset match on backend');
        }
    } catch (error) {
        console.error('❌ Error resetting match:', error);
    }

    // 2. Reset game mode on backend (set to null)
    try {
        const modeResponse = await fetch(`${API_BASE}/setgamemode`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: null })
        });
        const modeData = await modeResponse.json();
        if (modeData.success) {
            console.log('✅ Game mode reset successfully on backend (null)');
        } else {
            console.error('❌ Failed to reset game mode on backend');
        }
    } catch (error) {
        console.error('❌ Error resetting game mode:', error);
    }

    // 3. Reset local variables
    score1 = 0;
    score2 = 0;
    games1 = 0;
    games2 = 0;
    sets1 = 0;
    sets2 = 0;
    matchWon = false;
    winnerData = null;
    setsHistory = [];
    matchStartTime = Date.now();
    gameMode = null;            // Reset game mode
    isScoreboardActive = false; // Deactivate scoreboard
    pendingSensorEvents = [];   // Clear pending events

    // 4. Hide winner display
    if (winnerDisplay) {
        winnerDisplay.style.display = 'none';
    }

    // 5. Hide mode selection if visible
    const modeScreen = document.getElementById('modeSelectionScreen');
    if (modeScreen) {
        modeScreen.classList.remove('active');
        modeScreen.style.display = 'none';
    }

    // 6. Update scoreboard display
    updateDisplay();

    // 7. Reset splash dismissed flag
    splashDismissed = false;

    // 8. Show splash screen
    const splashScreen = document.getElementById('splashScreen');
    if (splashScreen) {
        splashScreen.classList.add('active');
        console.log('🎬 Match and mode reset complete - splash screen displayed');
    }
}

// =================================================================================================
// SCOREBOARD UPDATE HELPERS (unchanged core logic)
// =================================================================================================
function updateFromGameState(data) {
    score1 = data.score1;
    score2 = data.score2;
    games1 = data.game1;
    games2 = data.game2;
    sets1 = data.set1;
    sets2 = data.set2;
    matchWon = data.matchwon;

    if (data.gamemode !== undefined) {
        gameMode = data.gamemode;
    }

    updateDisplay();
}

function updateDisplay() {
    const scoreEl1 = document.getElementById('score1');
    const scoreEl2 = document.getElementById('score2');
    const gamesEl1 = document.getElementById('games1');
    const gamesEl2 = document.getElementById('games2');
    const setsEl1 = document.getElementById('sets1');
    const setsEl2 = document.getElementById('sets2');

    if (scoreEl1) scoreEl1.textContent = score1;
    if (scoreEl2) scoreEl2.textContent = score2;
    if (gamesEl1) gamesEl1.textContent = games1;
    if (gamesEl2) gamesEl2.textContent = games2;
    if (setsEl1) setsEl1.textContent = sets1;
    if (setsEl2) setsEl2.textContent = sets2;
}

// =================================================================================================
// CLICKABLE TEAMS / MANUAL CONTROL (if used)
// =================================================================================================
function setupClickableTeams() {
    const blackTeam = document.getElementById('blackTeam');
    const yellowTeam = document.getElementById('yellowTeam');

    if (blackTeam) {
        blackTeam.addEventListener('click', () => {
            if (!isScoreboardActive || !gameMode) {
                console.log('⛔ Scoreboard not active yet - ignoring manual black click');
                return;
            }
            manualAddPoint('black');
        });
    }

    if (yellowTeam) {
        yellowTeam.addEventListener('click', () => {
            if (!isScoreboardActive || !gameMode) {
                console.log('⛔ Scoreboard not active yet - ignoring manual yellow click');
                return;
            }
            manualAddPoint('yellow');
        });
    }
}

async function manualAddPoint(team) {
    try {
        const resp = await fetch(`${API_BASE}/addpoint`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ team })
        });
        const data = await resp.json();
        console.log('🖱️ Manual add point:', data);
    } catch (err) {
        console.error('Error adding point manually:', err);
    }
}

// =================================================================================================
// WINNER DISPLAY
// =================================================================================================
function displayWinner(data) {
    winnerData = data;
    const winnerDisplay = document.getElementById('winnerDisplay');
    if (!winnerDisplay) return;

    const winnerTeamNameEl = document.getElementById('winnerTeamName');
    const finalSetsScoreEl = document.getElementById('finalSetsScore');
    const matchDurationEl = document.getElementById('matchDuration');

    if (winnerTeamNameEl && data.winner && data.winner.teamname) {
        winnerTeamNameEl.textContent = data.winner.teamname;
    }

    if (finalSetsScoreEl && data.winner && data.winner.finalsets) {
        finalSetsScoreEl.textContent = data.winner.finalsets;
    }

    if (matchDurationEl && data.winner && data.winner.matchduration) {
        matchDurationEl.textContent = data.winner.matchduration;
    }

    winnerDisplay.style.display = 'flex';
    console.log('🏆 Winner display shown');

    clearWinnerTimeout();
    winnerDismissTimeout = setTimeout(() => {
        console.log('⏱️ Auto-dismiss winner screen after timeout');
        resetMatchAndGoToSplash();
    }, 60000); // 1 minute
}

// =================================================================================================
// TOAST NOTIFICATIONS
// =================================================================================================
function showToast(action, team, gameState) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const teamName = team === 'black' ? 'BLACK' : 'YELLOW';

    let icon = '🎯';
    let title = 'POINT SCORED';
    let message = `${teamName} team scored!`;
    let toastType = 'toast-point';

    if (action === 'game') {
        icon = '🎾';
        title = 'GAME WON';
        message = `${teamName} wins the game! ${gameState.game1}-${gameState.game2}`;
        toastType = 'toast-game';
    } else if (action === 'set') {
        icon = '🏅';
        title = 'SET WON';
        message = `${teamName} wins the set! Sets: ${gameState.set1}-${gameState.set2}`;
        toastType = 'toast-set';
    } else if (action === 'match') {
        icon = '🏆';
        title = 'MATCH WON';
        message = `${teamName} wins the match!`;
        toastType = 'toast-match';
    }

    const toast = document.createElement('div');
    toast.className = `toast ${toastType}`;
    toast.innerHTML = `
        <div class="toast-icon">${icon}</div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close">×</button>
    `;

    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => {
        toast.remove();
    });

    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4000);
}

// =================================================================================================
// CLICK FEEDBACK (visual flash on team section)
// =================================================================================================
function showClickFeedback(team) {
    const el = team === 'black'
        ? document.querySelector('.black-team')
        : document.querySelector('.yellow-team');

    if (!el) return;

    el.classList.add('team-clicked');
    setTimeout(() => {
        el.classList.remove('team-clicked');
    }, 150);
}

// =================================================================================================
// LOGO SETUP (if you have logo click behavior)
// =================================================================================================
function setupLogo() {
    const logo = document.getElementById('logoContainer');
    if (!logo) return;

    logo.addEventListener('click', () => {
        console.log('🎨 Logo clicked');
    });
}
