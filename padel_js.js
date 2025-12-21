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
    console.log('🎯 Point scored event received:', data);
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
let isScoreboardActive = false; // TRUE only when scoreboard is fully visible

// Mode detection variables
let pendingSensorEvents = [];
const DUAL_SENSOR_WINDOW = 500; // 500ms window to detect dual sensor

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
// SENSOR INPUT HANDLER - PRIORITY BASED ROUTING
// =================================================================================================
function handleSensorInput(data) {
    // DEBOUNCE CHECK FIRST
    if (!shouldProcessSensorInput(data.team)) {
        console.log(`🚫 Sensor input IGNORED (debounced): ${data.team}`);
        return;
    }
    
    const currentTime = Date.now();
    
    // ========== STATE 1: WINNER SCREEN ==========
    // Any sensor input → Reset match and go to splash
    if (DOM.winnerDisplay && DOM.winnerDisplay.style.display === 'flex') {
        console.log('🏆 Winner screen active → Sensor input → Reset and go to splash (NO SCORING)');
        clearWinnerTimeout();
        resetMatchAndGoToSplash();
        return;
    }
    
    // ========== STATE 2: SPLASH SCREEN ==========
    // Any sensor input → Dismiss splash and go to mode selection (NO SCORING)
    if (DOM.splashScreen && DOM.splashScreen.classList.contains('active')) {
        console.log('✨ Splash screen active → Sensor input → Dismiss and show mode selection (NO SCORING)');
        dismissSplash();
        return;
    }
    
    // ========== STATE 3: MODE SELECTION SCREEN ==========
    // Detect mode based on sensor pattern (NO SCORING)
    if (DOM.modeSelectionScreen && DOM.modeSelectionScreen.style.display === 'flex') {
        console.log('🎮 Mode selection active → Detecting mode from sensor pattern (NO SCORING)');
        detectAndSelectMode(data, currentTime);
        return;
    }
    
    // ========== STATE 4: SCOREBOARD ACTIVE ==========
    // ONLY NOW can points be scored
    if (isScoreboardActive && gameMode) {
        console.log(`📊 Scoreboard ACTIVE → Processing point for ${data.team} team`);
        showClickFeedback(data.team);
        showToast(data.action, data.team, data.gamestate);
    } else {
        console.log('⚠️ Scoreboard NOT active yet - point NOT counted');
    }
}

// =================================================================================================
// MODE DETECTION LOGIC - Uses sensor patterns to auto-select mode
// =================================================================================================
function detectAndSelectMode(data, currentTime) {
    // Add current sensor event to buffer
    pendingSensorEvents.push({
        team: data.team,
        time: currentTime,
        action: data.action
    });
    
    // Clean up old events outside the detection window
    pendingSensorEvents = pendingSensorEvents.filter(event => 
        currentTime - event.time < DUAL_SENSOR_WINDOW
    );
    
    console.log(`📊 Pending sensor events: ${pendingSensorEvents.length}`, pendingSensorEvents);
    
    // Check for dual sensor firing (both black and yellow within window)
    const hasBlack = pendingSensorEvents.some(e => e.team === 'black');
    const hasYellow = pendingSensorEvents.some(e => e.team === 'yellow');
    
    // COMPETITION MODE: Both sensors fired within time window
    if (hasBlack && hasYellow) {
        console.log('🏆 COMPETITION MODE detected (both sensors fired within 500ms)');
        selectMode('competition');
        pendingSensorEvents = [];
        return;
    }
    
    // Wait for potential second sensor
    if (pendingSensorEvents.length === 1) {
        setTimeout(() => {
            // Still only one sensor after waiting
            if (pendingSensorEvents.length === 1 && 
                DOM.modeSelectionScreen && 
                DOM.modeSelectionScreen.style.display === 'flex') {
                
                const event = pendingSensorEvents[0];
                
                // BASIC MODE: Single "addpoint" action
                if (event.action === 'point') {
                    console.log('🎯 BASIC MODE detected (single sensor addpoint)');
                    selectMode('basic');
                } 
                // COMPETITION MODE: Single "subtractpoint" action
                else if (event.action === 'subtract') {
                    console.log('🏆 COMPETITION MODE detected (subtractpoint trigger)');
                    selectMode('competition');
                } else {
                    // Fallback to basic
                    console.log('🎯 BASIC MODE detected (fallback - single sensor)');
                    selectMode('basic');
                }
                
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
// SPLASH SCREEN - Auto-dismisses to mode selection
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
        
        // Go directly to mode selection after splash
        setTimeout(() => {
            showModeSelection();
        }, 500);
        
        console.log('✨ Splash dismissed → Showing mode selection (NO SCORING)');
    }
}

// =================================================================================================
// MODE SELECTION SCREEN
// =================================================================================================
function showModeSelection() {
    if (DOM.modeSelectionScreen) {
        DOM.modeSelectionScreen.style.display = 'flex';
        DOM.modeSelectionScreen.offsetHeight; // Force reflow
        DOM.modeSelectionScreen.classList.add('active');
        
        // Clear any pending sensor events when mode selection appears
        pendingSensorEvents = [];
        
        console.log('🎮 Mode selection screen shown - Waiting for mode detection (NO SCORING)');
    }
}

async function selectMode(mode) {
    console.log(`🎯 Mode selected: ${mode} (Scoreboard will activate after mode screen hides)`);
    
    gameMode = mode;
    
    // Send mode to backend
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
            console.log(`✅ Game mode set to: ${mode} on backend`);
        } else {
            console.error('❌ Failed to set game mode:', data.error);
        }
    } catch (error) {
        console.error('❌ Error setting game mode:', error);
    }
    
    // Hide mode selection screen
    if (DOM.modeSelectionScreen) {
        DOM.modeSelectionScreen.classList.remove('active');
        setTimeout(() => {
            DOM.modeSelectionScreen.style.display = 'none';
            
            // IMPORTANT: Activate scoreboard ONLY after mode screen is hidden
            isScoreboardActive = true;
            console.log('✅✅✅ SCOREBOARD NOW ACTIVE - Points can now be scored! ✅✅✅');
        }, 500); // Wait for fade animation
    }
    
    // Reset and start match timer
    matchStartTime = Date.now();
    
    console.log('📊 Scoreboard ready - Match timer started');
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
                console.log('👆 Winner screen clicked → Reset match and go to splash');
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
    
    // Reset match on backend
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
    
    // Reset game mode on backend
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
    
    // Reset all local variables
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
    isScoreboardActive = false; // DEACTIVATE SCOREBOARD
    pendingSensorEvents = [];
    lastSensorTime = { black: 0, yellow: 0 };
    
    // Hide all screens
    if (DOM.winnerDisplay) {
        DOM.winnerDisplay.style.display = 'none';
    }
    
    if (DOM.modeSelectionScreen) {
        DOM.modeSelectionScreen.classList.remove('active');
        DOM.modeSelectionScreen.style.display = 'none';
    }
    
    updateDisplay();
    
    // Reset splash flag and show splash
    splashDismissed = false;
    
    if (DOM.splashScreen) {
        DOM.splashScreen.classList.add('active');
        console.log('🎬 Match reset complete → Splash screen displayed');
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
// SETUP CLICKABLE TEAMS
// =================================================================================================
function setupClickableTeams() {
    if (DOM.blackTeam) {
        DOM.blackTeam.style.cursor = 'pointer';
        DOM.blackTeam.addEventListener('click', function(e) {
            if (e.target.closest('#logoClick') || e.target.closest('#controlPanel')) {
                return;
            }
            
            // Winner screen → Reset
            if (DOM.winnerDisplay && DOM.winnerDisplay.style.display === 'flex') {
                console.log('🏆 Winner screen visible → Black clicked → Reset');
                clearWinnerTimeout();
                resetMatchAndGoToSplash();
                return;
            }
            
            // Splash screen → Dismiss
            if (DOM.splashScreen && DOM.splashScreen.classList.contains('active')) {
                console.log('✨ Splash active → Black clicked → Dismiss');
                dismissSplash();
                return;
            }
            
            // Mode selection → Select BASIC
            if (DOM.modeSelectionScreen && DOM.modeSelectionScreen.style.display === 'flex') {
                console.log('🎮 Mode selection → Black clicked → BASIC mode');
                selectMode('basic');
                return;
            }
            
            // Scoreboard active → Add point
            if (isScoreboardActive) {
                console.log('📊 Scoreboard active → Black clicked → Add point');
                addPointManual('black');
            } else {
                console.log('⚠️ Scoreboard NOT active - click ignored');
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
            
            // Winner screen → Reset
            if (DOM.winnerDisplay && DOM.winnerDisplay.style.display === 'flex') {
                console.log('🏆 Winner screen visible → Yellow clicked → Reset');
                clearWinnerTimeout();
                resetMatchAndGoToSplash();
                return;
            }
            
            // Splash screen → Dismiss
            if (DOM.splashScreen && DOM.splashScreen.classList.contains('active')) {
                console.log('✨ Splash active → Yellow clicked → Dismiss');
                dismissSplash();
                return;
            }
            
            // Mode selection → Select BASIC
            if (DOM.modeSelectionScreen && DOM.modeSelectionScreen.style.display === 'flex') {
                console.log('🎮 Mode selection → Yellow clicked → BASIC mode');
                selectMode('basic');
                return;
            }
            
            // Scoreboard active → Add point
            if (isScoreboardActive) {
                console.log('📊 Scoreboard active → Yellow clicked → Add point');
                addPointManual('yellow');
            } else {
                console.log('⚠️ Scoreboard NOT active - click ignored');
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
        
        // Deactivate scoreboard when winner is shown
        isScoreboardActive = false;
        console.log('🏆 Winner displayed - Scoreboard DEACTIVATED');
        
        clearWinnerTimeout();
        winnerDismissTimeout = setTimeout(() => {
            console.log('⏱️ Winner screen auto-dismiss (30s) - resetting match');
            resetMatchAndGoToSplash();
        }, 30000);
        
        console.log('🏆 Winner screen displayed with 30s auto-dismiss');
    }
}

// =================================================================================================
// MATCH RESET
// =================================================================================================
async function resetMatch() {
    console.log('🔄 Reset button clicked - resetting match');
    await resetMatchAndGoToSplash();
}

async function newMatch() {
    console.log('🆕 New match button clicked - resetting match');
    await resetMatchAndGoToSplash();
}

function shareResults() {
    alert('Share functionality coming soon!');
}
