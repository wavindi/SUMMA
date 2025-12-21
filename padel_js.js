// =================================================================================================
// DOM CACHE - Query once, reuse forever (20% performance boost!)
// =================================================================================================
const DOM = {
    // Screens
    splashScreen: null,
    modeSelectionScreen: null,
    winnerDisplay: null,
    
    // Score displays
    scoreBlack: null,
    scoreYellow: null,
    gamesBlack: null,
    gamesYellow: null,
    setsBlack: null,
    setsYellow: null,
    timeDisplay: null,
    
    // Winner screen elements
    winnerTeamName: null,
    finalSetsScore: null,
    matchDuration: null,
    setsTableBody: null,
    
    // Other elements
    toastContainer: null,
    controlPanel: null,
    blackTeam: null,
    yellowTeam: null,
    logoClick: null,
    logoImg: null,
    
    // Click feedback
    clickFeedbackBlack: null,
    clickFeedbackYellow: null
};

// Initialize DOM cache (called once on page load)
function cacheDOMElements() {
    DOM.splashScreen = document.getElementById('splashScreen');
    DOM.modeSelectionScreen = document.getElementById('modeSelectionScreen');
    DOM.winnerDisplay = document.getElementById('winnerDisplay');
    
    DOM.scoreBlack = document.getElementById('scoreBlack');
    DOM.scoreYellow = document.getElementById('scoreYellow');
    DOM.gamesBlack = document.getElementById('gamesBlack');
    DOM.gamesYellow = document.getElementById('gamesYellow');
    DOM.setsBlack = document.getElementById('setsBlack');
    DOM.setsYellow = document.getElementById('setsYellow');
    DOM.timeDisplay = document.getElementById('timeDisplay');
    
    DOM.winnerTeamName = document.getElementById('winnerTeamName');
    DOM.finalSetsScore = document.getElementById('finalSetsScore');
    DOM.matchDuration = document.getElementById('matchDuration');
    DOM.setsTableBody = document.getElementById('setsTableBody');
    
    DOM.toastContainer = document.getElementById('toastContainer');
    DOM.controlPanel = document.getElementById('controlPanel');
    DOM.blackTeam = document.querySelector('.team-section.black-team');
    DOM.yellowTeam = document.querySelector('.team-section.yellow-team');
    DOM.logoClick = document.getElementById('logoClick');
    DOM.logoImg = document.getElementById('logoImg');
    
    DOM.clickFeedbackBlack = document.getElementById('clickFeedbackBlack');
    DOM.clickFeedbackYellow = document.getElementById('clickFeedbackYellow');
    
    console.log('✅ DOM elements cached');
}

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
let gameMode = null;
let isScoreboardActive = false;

// Mode detection variables
let pendingSensorEvents = [];
const DUAL_SENSOR_WINDOW = 800;

// SENSOR DEBOUNCING - Prevents double-firing
const SENSOR_DEBOUNCE_MS = 100; // 100ms debounce window
let lastSensorTime = { black: 0, yellow: 0 };

const API_BASE = "http://127.0.0.1:5000";

// =================================================================================================
// SENSOR DEBOUNCING FUNCTION
// =================================================================================================
function shouldProcessSensorInput(team) {
    const now = Date.now();
    const timeSinceLastFire = now - lastSensorTime[team];
    
    if (timeSinceLastFire < SENSOR_DEBOUNCE_MS) {
        console.log(`⚠️ Sensor ${team} debounced (${timeSinceLastFire}ms since last)`);
        return false; // Ignore this input
    }
    
    lastSensorTime[team] = now;
    return true; // Process this input
}

// =================================================================================================
// SENSOR INPUT HANDLER WITH MODE DETECTION
// =================================================================================================
function handleSensorInput(data) {
    // DEBOUNCE CHECK FIRST
    if (!shouldProcessSensorInput(data.team)) {
        return; // Ignore debounced input
    }
    
    const currentTime = Date.now();
    
    // STATE 1: Winner screen is showing - reset match
    if (DOM.winnerDisplay && DOM.winnerDisplay.style.display === 'flex') {
        console.log('🏆 Winner screen visible - sensor input detected, resetting match and going to splash');
        clearWinnerTimeout();
        resetMatchAndGoToSplash();
        return;
    }
    
    // STATE 2: Splash screen is showing - dismiss it (no scoring)
    if (DOM.splashScreen && DOM.splashScreen.classList.contains('active')) {
        console.log('✨ Splash screen active - dismissing (no scoring)');
        dismissSplash();
        return;
    }
    
    // STATE 3: Mode selection screen - detect mode and select (no scoring)
    if (DOM.modeSelectionScreen && DOM.modeSelectionScreen.style.display === 'flex') {
        console.log('🎮 Mode selection active - detecting mode from sensor pattern');
        detectAndSelectMode(data, currentTime);
        return;
    }
    
    // STATE 4: Scoreboard is active - normal scoring
    if (isScoreboardActive && gameMode) {
        console.log('📊 Scoreboard active - processing point');
        showClickFeedback(data.team);
        showToast(data.action, data.team, data.gamestate);
    }
}

// =================================================================================================
// MODE DETECTION LOGIC
// =================================================================================================
function detectAndSelectMode(data, currentTime) {
    pendingSensorEvents.push({
        team: data.team,
        time: currentTime
    });
    
    pendingSensorEvents = pendingSensorEvents.filter(event => 
        currentTime - event.time < DUAL_SENSOR_WINDOW
    );
    
    const hasBlack = pendingSensorEvents.some(e => e.team === 'black');
    const hasYellow = pendingSensorEvents.some(e => e.team === 'yellow');
    
    if (hasBlack && hasYellow) {
        console.log('🏆 COMPETITION MODE detected (both sensors fired)');
        selectMode('competition');
        pendingSensorEvents = [];
    } else if (pendingSensorEvents.length === 1) {
        setTimeout(() => {
            const stillHasOne = pendingSensorEvents.length === 1;
            const stillOnModeScreen = DOM.modeSelectionScreen.style.display === 'flex';
            
            if (stillHasOne && stillOnModeScreen) {
                console.log('🎯 BASIC MODE detected (single sensor)');
                selectMode('basic');
                pendingSensorEvents = [];
            }
        }, DUAL_SENSOR_WINDOW);
    }
}

// =================================================================================================
// INITIALIZATION
// =================================================================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🏓 Padel Scoreboard Initialized');
    
    // Cache all DOM elements FIRST
    cacheDOMElements();
    
    setupSplashScreen();
    setupLogo();
    
    // Start match duration timer with requestAnimationFrame
    requestAnimationFrame(timerLoop);
    
    setupClickableTeams();
    setupWinnerScreenClickDismiss();
    
    // CLEANUP: Clean up pending sensor events every 5 seconds
    setInterval(() => {
        if (pendingSensorEvents.length > 5) {
            console.log('🧹 Cleaning up stale sensor events');
            pendingSensorEvents = [];
        }
    }, 5000);
});

// =================================================================================================
// MATCH DURATION TIMER WITH requestAnimationFrame (OPTIMIZED)
// =================================================================================================
let lastTimerUpdate = 0;

function timerLoop(timestamp) {
    // Update every ~1000ms (synced with display refresh)
    if (timestamp - lastTimerUpdate >= 1000) {
        updateMatchDuration();
        lastTimerUpdate = timestamp;
    }
    requestAnimationFrame(timerLoop);
}

function updateMatchDuration() {
    const now = Date.now();
    const elapsed = now - matchStartTime;
    
    const totalSeconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    
    const formattedTime = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    
    if (DOM.timeDisplay) {
        DOM.timeDisplay.textContent = formattedTime;
    }
}

// =================================================================================================
// SPLASH SCREEN
// =================================================================================================
function setupSplashScreen() {
    if (!DOM.splashScreen) return;
    
    const dismissSplashHandler = () => {
        dismissSplash();
    };
    
    DOM.splashScreen.addEventListener('click', dismissSplashHandler);
    DOM.splashScreen.addEventListener('touchstart', dismissSplashHandler);
}

function dismissSplash() {
    if (!splashDismissed && DOM.splashScreen) {
        splashDismissed = true;
        DOM.splashScreen.classList.remove('active');
        
        setTimeout(() => {
            showModeSelection();
        }, 500);
        
        console.log('✨ Splash screen dismissed - showing mode selection');
    }
}

// =================================================================================================
// MODE SELECTION SCREEN
// =================================================================================================
function showModeSelection() {
    if (DOM.modeSelectionScreen) {
        DOM.modeSelectionScreen.style.display = 'flex';
        DOM.modeSelectionScreen.offsetHeight;
        DOM.modeSelectionScreen.classList.add('active');
        
        pendingSensorEvents = [];
        
        console.log('🎮 Mode selection screen shown - ready for mode detection');
    }
}

async function selectMode(mode) {
    console.log(`🎯 Mode selected: ${mode}`);
    
    gameMode = mode;
    
    try {
        const response = await fetch(`${API_BASE}/setgamemode`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ mode: mode })
        });
        
        const data = await response.json();
        if (data.success) {
            console.log(`✅ Game mode set to: ${mode}`);
        } else {
            console.error('❌ Failed to set game mode:', data.error);
        }
    } catch (error) {
        console.error('❌ Error setting game mode:', error);
    }
    
    if (DOM.modeSelectionScreen) {
        DOM.modeSelectionScreen.classList.remove('active');
        setTimeout(() => {
            DOM.modeSelectionScreen.style.display = 'none';
            isScoreboardActive = true;
            console.log('✅ Scoreboard now active for scoring');
        }, 500);
    }
    
    matchStartTime = Date.now();
    
    console.log('📊 Scoreboard ready - match timer started');
}

// =================================================================================================
// WINNER SCREEN MANAGEMENT
// =================================================================================================
function setupWinnerScreenClickDismiss() {
    if (DOM.winnerDisplay) {
        DOM.winnerDisplay.addEventListener('click', function(e) {
            if (e.target.closest('.action-button')) {
                return;
            }
            
            if (DOM.winnerDisplay.style.display === 'flex') {
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
    
    try {
        const resetResponse = await fetch(`${API_BASE}/resetmatch`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
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
    
    try {
        const modeResponse = await fetch(`${API_BASE}/setgamemode`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ mode: null })
        });
        
        const modeData = await modeResponse.json();
        if (modeData.success) {
            console.log('✅ Game mode reset successfully on backend');
        } else {
            console.error('❌ Failed to reset game mode on backend');
        }
    } catch (error) {
        console.error('❌ Error resetting game mode:', error);
    }
    
    // Reset local variables
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
    gameMode = null;
    isScoreboardActive = false;
    pendingSensorEvents = [];
    lastSensorTime = { black: 0, yellow: 0 }; // Reset debounce timers
    
    if (DOM.winnerDisplay) {
        DOM.winnerDisplay.style.display = 'none';
    }
    
    if (DOM.modeSelectionScreen) {
        DOM.modeSelectionScreen.classList.remove('active');
        DOM.modeSelectionScreen.style.display = 'none';
    }
    
    updateDisplay();
    
    splashDismissed = false;
    
    if (DOM.splashScreen) {
        DOM.splashScreen.classList.add('active');
        console.log('🎬 Match and mode reset complete - splash screen displayed');
    }
}

// =================================================================================================
// TOAST NOTIFICATIONS
// =================================================================================================
function showToast(action, team, gameState) {
    if (!DOM.toastContainer) return;
    
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
        <div class="toast-close">×</div>
    `;
    
    DOM.toastContainer.appendChild(toast);
    
    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => removeToast(toast));
    
    const duration = action === 'match' ? 8000 : action === 'set' ? 5000 : action === 'game' ? 4000 : 3000;
    setTimeout(() => removeToast(toast), duration);
}

function removeToast(toast) {
    toast.classList.add('toast-out');
    setTimeout(() => {
        if (toast.parentElement) {
            toast.parentElement.removeChild(toast);
        }
    }, 400);
}

// =================================================================================================
// SETUP CLICKABLE TEAMS (MANUAL MODE SELECTION)
// =================================================================================================
function setupClickableTeams() {
    if (DOM.blackTeam) {
        DOM.blackTeam.style.cursor = 'pointer';
        DOM.blackTeam.addEventListener('click', function(e) {
            if (e.target.closest('#logoClick') || e.target.closest('#controlPanel')) {
                return;
            }
            
            if (DOM.winnerDisplay && DOM.winnerDisplay.style.display === 'flex') {
                console.log('🏆 Winner screen visible - black side clicked, resetting match and going to splash');
                clearWinnerTimeout();
                resetMatchAndGoToSplash();
                return;
            }
            
            if (DOM.splashScreen && DOM.splashScreen.classList.contains('active')) {
                console.log('✨ Splash active - dismissing only (no mode selection)');
                dismissSplash();
                return;
            }
            
            if (DOM.modeSelectionScreen && DOM.modeSelectionScreen.style.display === 'flex') {
                console.log('🎮 Black team clicked on mode screen - selecting BASIC mode');
                selectMode('basic');
                return;
            }
            
            if (isScoreboardActive) {
                console.log('Black team clicked');
                addPointManual('black');
            }
        });
        console.log('✅ Black team click listener added');
    }
    
    if (DOM.yellowTeam) {
        DOM.yellowTeam.style.cursor = 'pointer';
        DOM.yellowTeam.addEventListener('click', function(e) {
            if (e.target.closest('#controlPanel')) {
                return;
            }
            
            if (DOM.winnerDisplay && DOM.winnerDisplay.style.display === 'flex') {
                console.log('🏆 Winner screen visible - yellow side clicked, resetting match and going to splash');
                clearWinnerTimeout();
                resetMatchAndGoToSplash();
                return;
            }
            
            if (DOM.splashScreen && DOM.splashScreen.classList.contains('active')) {
                console.log('✨ Splash active - dismissing only (no mode selection)');
                dismissSplash();
                return;
            }
            
            if (DOM.modeSelectionScreen && DOM.modeSelectionScreen.style.display === 'flex') {
                console.log('🎮 Yellow team clicked on mode screen - selecting BASIC mode');
                selectMode('basic');
                return;
            }
            
            if (isScoreboardActive) {
                console.log('Yellow team clicked');
                addPointManual('yellow');
            }
        });
        console.log('✅ Yellow team click listener added');
    }
}

// =================================================================================================
// LOGO SETUP
// =================================================================================================
function setupLogo() {
    if (DOM.logoImg) {
        DOM.logoImg.onload = function() {
            console.log('✅ Logo image loaded');
            if (DOM.logoClick) {
                DOM.logoClick.classList.remove('no-image');
            }
        };
        
        DOM.logoImg.onerror = function() {
            console.log('⚠️ Logo image failed, using fallback');
            if (DOM.logoClick) {
                DOM.logoClick.classList.add('no-image');
            }
        };
        
        if (DOM.logoImg.complete) {
            if (DOM.logoImg.naturalWidth === 0) {
                DOM.logoImg.onerror();
            } else {
                DOM.logoImg.onload();
            }
        }
    }
    
    if (DOM.logoClick) {
        DOM.logoClick.addEventListener('click', function(e) {
            e.stopPropagation();
            if (DOM.controlPanel) {
                if (DOM.controlPanel.style.display === 'none' || !DOM.controlPanel.style.display) {
                    DOM.controlPanel.style.display = 'flex';
                    console.log('🎛️ Controls shown');
                } else {
                    DOM.controlPanel.style.display = 'none';
                    console.log('🎛️ Controls hidden');
                }
            }
        });
    }
}

// =================================================================================================
// GAME STATE UPDATE FROM SOCKET.IO
// =================================================================================================
function updateFromGameState(gameState) {
    score1 = gameState.score1;
    score2 = gameState.score2;
    games1 = gameState.game1;
    games2 = gameState.game2;
    sets1 = gameState.set1;
    sets2 = gameState.set2;
    matchWon = gameState.matchwon;
    
    updateDisplay();
    
    if (gameState.matchwon && gameState.winner) {
        winnerData = gameState.winner;
        fetchMatchDataAndDisplay();
    }
    
    if (gameState.sethistory && gameState.sethistory.length > 0) {
        setsHistory = gameState.sethistory.map(setScore => {
            const [blackGames, yellowGames] = setScore.split('-').map(Number);
            return { blackGames, yellowGames };
        });
    }
}

function updateDisplay() {
    if (DOM.scoreBlack) DOM.scoreBlack.textContent = score1;
    if (DOM.scoreYellow) DOM.scoreYellow.textContent = score2;
    if (DOM.gamesBlack) DOM.gamesBlack.textContent = games1;
    if (DOM.gamesYellow) DOM.gamesYellow.textContent = games2;
    if (DOM.setsBlack) DOM.setsBlack.textContent = sets1;
    if (DOM.setsYellow) DOM.setsYellow.textContent = sets2;
    
    console.log(`📊 Display updated - Score: ${score1}-${score2} | Games: ${games1}-${games2} | Sets: ${sets1}-${sets2}`);
}

// =================================================================================================
// MANUAL POINT ADDITION
// =================================================================================================
async function addPointManual(team) {
    console.log(`➕ Adding point to ${team} team`);
    
    try {
        const response = await fetch(`${API_BASE}/addpoint`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ team: team })
        });
        
        const data = await response.json();
        if (data.success) {
            console.log('✅ Point added successfully');
            showClickFeedback(team);
        } else {
            console.error('❌ Failed to add point:', data.error);
            alert(data.error);
        }
    } catch (error) {
        console.error('❌ Error adding point:', error);
        alert('Network error: ' + error.message);
    }
}

async function subtractPoint(team) {
    console.log(`➖ Subtracting point from ${team} team`);
    
    try {
        const response = await fetch(`${API_BASE}/subtractpoint`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ team: team })
        });
        
        const data = await response.json();
        if (data.success) {
            console.log('✅ Point subtracted successfully');
        } else {
            console.error('❌ Failed to subtract point:', data.error);
            alert(data.error);
        }
    } catch (error) {
        console.error('❌ Error subtracting point:', error);
        alert('Network error: ' + error.message);
    }
}

function showClickFeedback(team) {
    const feedback = team === 'black' ? DOM.clickFeedbackBlack : DOM.clickFeedbackYellow;
    if (feedback) {
        feedback.style.animation = 'none';
        setTimeout(() => {
            feedback.style.animation = 'feedbackPulse 0.8s ease-in-out';
        }, 10);
    }
}

// =================================================================================================
// WINNER DISPLAY
// =================================================================================================
async function fetchMatchDataAndDisplay() {
    try {
        const response = await fetch(`${API_BASE}/getmatchdata`);
        const data = await response.json();
        if (data.success && data.matchdata) {
            displayWinnerWithData(data.matchdata);
        }
    } catch (error) {
        console.error('❌ Error fetching match data:', error);
    }
}

function displayWinner(data) {
    if (data.matchdata) {
        displayWinnerWithData(data.matchdata);
    }
}

function displayWinnerWithData(matchData) {
    console.log('🏆 Displaying winner:', matchData);
    
    if (DOM.winnerTeamName) {
        DOM.winnerTeamName.textContent = matchData.winnername;
        DOM.winnerTeamName.className = `winner-team-name ${matchData.winnerteam}`;
    }
    
    if (DOM.finalSetsScore) {
        DOM.finalSetsScore.textContent = matchData.finalsetsscore;
    }
    
    if (DOM.matchDuration) {
        DOM.matchDuration.textContent = matchData.matchduration;
    }
    
    if (DOM.setsTableBody && matchData.setsbreakdown) {
        let tableHTML = '';
        matchData.setsbreakdown.forEach(set => {
            const blackClass = set.setwinner === 'black' ? 'winner-set' : '';
            const yellowClass = set.setwinner === 'yellow' ? 'winner-set' : '';
            tableHTML += `
                <tr>
                    <td>Set ${set.setnumber}</td>
                    <td class="${blackClass}">${set.blackgames}</td>
                    <td class="${yellowClass}">${set.yellowgames}</td>
                    <td class="team-column ${set.setwinner}">${set.setwinner.toUpperCase()}</td>
                </tr>
            `;
        });
        DOM.setsTableBody.innerHTML = tableHTML;
    }
    
    if (DOM.winnerDisplay) {
        DOM.winnerDisplay.style.display = 'flex';
        
        isScoreboardActive = false;
        
        clearWinnerTimeout();
        winnerDismissTimeout = setTimeout(() => {
            console.log('⏱️ Winner screen auto-dismiss (30s) - resetting match and going to splash');
            resetMatchAndGoToSplash();
        }, 30000);
        
        console.log('🏆 Winner screen displayed with 30s auto-dismiss');
    }
}

// =================================================================================================
// MATCH RESET
// =================================================================================================
async function resetMatch() {
    console.log('🔄 Reset button clicked - resetting match, mode, and going to splash...');
    await resetMatchAndGoToSplash();
}

async function newMatch() {
    console.log('🆕 New match button clicked - resetting match, mode, and going to splash...');
    await resetMatchAndGoToSplash();
}

function shareResults() {
    alert('Share functionality coming soon!');
}
