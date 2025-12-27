// ===== SOCKET.IO REAL-TIME CONNECTION =====
const socket = io("http://127.0.0.1:5000", {
    transports: ["polling", "websocket"],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 10
});

socket.on('connect', () => {
    console.log('✓ Connected to server via Socket.IO');
    socket.emit('request_gamestate');
});

socket.on('disconnect', () => {
    console.log('✗ Disconnected from server');
});

socket.on('gamestateupdate', (data) => {
    console.log('Game state update received:', data);
    updateFromGameState(data);
});

socket.on('pointscored', (data) => {
    console.log('Point scored:', data);
    handleSensorInput(data);
});

socket.on('matchwon', (data) => {
    console.log('Match won:', data);
    displayWinner(data);
});

socket.on('sideswitchrequired', (data) => {
    console.log('Side switch required:', data);
    handleSideSwitch(data);
});

// ===== GAME VARIABLES =====
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
let stageTimeout = null;
let gameMode = null;
let isScoreboardActive = false;
let matchWonFlag = false;  // Flag to prevent side switch after match won

const API_BASE = "http://127.0.0.1:5000";

// ===== SENSOR INPUT HANDLER =====
function handleSensorInput(data) {
    const currentTime = Date.now();

    // STATE 1: Winner screen is showing - reset match
    const winnerDisplay = document.getElementById('winnerDisplay');
    if (winnerDisplay && winnerDisplay.style.display === 'flex') {
        console.log('Winner screen visible - sensor input detected, resetting match and going to splash');
        clearWinnerTimeout();
        resetMatchAndGoToSplash();
        return;
    }

    // STATE 2: Splash screen is showing - go directly to GAME MODE screen (NO SCORING)
    const splashScreen = document.getElementById('splashScreen');
    if (splashScreen && splashScreen.classList.contains('active')) {
        console.log('Splash screen active - going to GAME MODE screen (NO SCORING)');
        dismissSplash();
        return;
    }

    // STATE 3: Mode selection screen - handle addpoint/subtractpoint
    const modeScreen = document.getElementById('modeSelectionScreen');
    if (modeScreen && modeScreen.style.display === 'flex') {
        console.log('Game mode screen active - handling sensor input');
        if (data.action === 'addpoint') {
            console.log('addpoint detected on game mode screen - selecting BASIC mode (NO SCORING)');
            selectMode('basic');
        } else if (data.action === 'subtractpoint') {
            console.log('subtractpoint detected on game mode screen - selecting COMPETITION mode (NO SCORING)');
            selectMode('competition');
        }
        return;
    }

    // STATE 4: Scoreboard is active - normal scoring
    if (isScoreboardActive && gameMode) {
        console.log('Scoreboard active - processing point');
        showClickFeedback(data.team);
        showToast(data.action, data.team, data.gamestate);
    }
}

// ===== SIDE SWITCH HANDLER (FULL-SCREEN RESPONSIVE) =====
function handleSideSwitch(data) {
    // IGNORE side switch if match is already won
    if (matchWonFlag) {
        console.log('⛔ Side switch ignored - match already won');
        return;
    }
    
    console.log('🔄 CHANGE SIDES - Total games:', data.totalgames, 'Score:', data.gamescore, 'Sets:', data.setscore);
    showSideSwitchNotification(data);
}

function showSideSwitchNotification(data) {
    const existing = document.getElementById('sideSwitchNotification');
    if (existing) {
        existing.remove();
    }
    
    const notification = document.createElement('div');
    notification.id = 'sideSwitchNotification';
    notification.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0, 0, 0, 0.75);
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        z-index: 10000;
        animation: fadeIn 0.3s ease-in;
    `;
    
    notification.innerHTML = `
        <div style="text-align: center; color: white; width: 100%; padding: 0 5vw;">
            <div style="font-size: 25vh; margin-bottom: 4vh; line-height: 1;">🔄</div>
            <div style="font-size: 12vh; font-weight: bold; margin-bottom: 6vh; text-transform: uppercase; letter-spacing: 0.5vw; text-shadow: 0 0 20px rgba(0,0,0,0.8);">CHANGE SIDES!</div>
            <div style="font-size: 8vh; opacity: 0.9; margin-top: 5vh; font-weight: 600; text-shadow: 0 0 15px rgba(0,0,0,0.8);">Games: ${data.gamescore}</div>
            <div style="font-size: 8vh; opacity: 0.9; margin-top: 3vh; font-weight: 600; text-shadow: 0 0 15px rgba(0,0,0,0.8);">Sets: ${data.setscore}</div>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    console.log('🔄 Side switch notification displayed (FULLSCREEN - TRANSPARENT):', data);
    
    setTimeout(() => {
        notification.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => {
            if (notification.parentElement) {
                notification.parentElement.removeChild(notification);
                console.log('✅ Side switch notification dismissed');
            }
        }, 300);
    }, 5000);
}

// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', function() {
    console.log('Padel Scoreboard Initialized - AUTO SKIPPING TO GAME MODE');
    
    setTimeout(() => {
        console.log('Auto-skipping splash - going directly to game mode screen');
        dismissSplash();
    }, 1000);
    
    setupLogo();
    updateMatchDuration();
    setInterval(updateMatchDuration, 1000);
    setupClickableTeams();
    setupWinnerScreenClickDismiss();
});

// ===== SPLASH SCREEN =====
function dismissSplash() {
    if (!splashDismissed) {
        splashDismissed = true;
        const splashScreen = document.getElementById('splashScreen');
        const scoreboard = document.querySelector('.scoreboard');
        
        if (scoreboard) {
            scoreboard.classList.add('hidden');
        }
        
        splashScreen.classList.remove('active');
        setTimeout(() => {
            showModeSelection();
        }, 300);
        
        console.log('Splash dismissed - scoreboard hidden immediately');
    }
}

// ===== MODE SELECTION SCREEN =====
function showModeSelection() {
    const modeScreen = document.getElementById('modeSelectionScreen');
    const scoreboard = document.querySelector('.scoreboard');
    
    if (modeScreen) {
        if (scoreboard) {
            scoreboard.classList.add('hidden');
        }
        
        modeScreen.style.display = 'flex';
        modeScreen.offsetHeight;
        modeScreen.classList.add('active');
        console.log('GAME MODE screen shown - scoreboard hidden');
    }
}

async function selectMode(mode) {
    console.log(`Mode selected: ${mode} - activating scoreboard`);
    gameMode = mode;
    
    try {
        const response = await fetch(`${API_BASE}/setgamemode`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
        const data = await response.json();
        if (data.success) {
            console.log(`Game mode set to ${mode} on backend`);
        } else {
            console.error('Failed to set game mode:', data.error);
        }
    } catch (error) {
        console.error('Error setting game mode:', error);
    }
    
    const modeScreen = document.getElementById('modeSelectionScreen');
    const scoreboard = document.querySelector('.scoreboard');
    
    if (modeScreen) {
        modeScreen.classList.remove('active');
        setTimeout(() => {
            modeScreen.style.display = 'none';
            
            if (scoreboard) {
                scoreboard.classList.remove('hidden');
                isScoreboardActive = true;
                console.log('SCOREBOARD NOW ACTIVE and VISIBLE - points will count');
            }
        }, 500);
    }
    
    matchStartTime = Date.now();
    console.log('Scoreboard ready - match timer started');
}

// ===== MATCH DURATION TIMER =====
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

// ===== WINNER SCREEN MANAGEMENT =====
function setupWinnerScreenClickDismiss() {
    const winnerDisplay = document.getElementById('winnerDisplay');
    if (winnerDisplay) {
        winnerDisplay.addEventListener('click', function(e) {
            clearWinnerTimeout();
            resetMatchAndGoToSplash();
        });
        console.log('Winner screen click-to-dismiss enabled');
    }
}

function clearWinnerTimeout() {
    if (winnerDismissTimeout) {
        clearTimeout(winnerDismissTimeout);
        winnerDismissTimeout = null;
    }
    if (stageTimeout) {
        clearTimeout(stageTimeout);
        stageTimeout = null;
    }
}

async function resetMatchAndGoToSplash() {
    console.log('Resetting match, mode, sensors, and going to splash...');
    
    try {
        const resetResponse = await fetch(`${API_BASE}/resetmatch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const resetData = await resetResponse.json();
        if (resetData.success) {
            console.log('Match reset successfully on backend');
        }
    } catch (error) {
        console.error('Error resetting match:', error);
    }
    
    try {
        const modeResponse = await fetch(`${API_BASE}/setgamemode`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: null })
        });
        const modeData = await modeResponse.json();
        if (modeData.success) {
            console.log('Game mode reset successfully on backend');
        }
    } catch (error) {
        console.error('Error resetting game mode:', error);
    }
    
    // Reset sensors to default positions
    try {
        const sensorResponse = await fetch(`${API_BASE}/resetsensors`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const sensorData = await sensorResponse.json();
        if (sensorData.success) {
            console.log('📡 Sensors reset to default positions');
        }
    } catch (error) {
        console.error('Error resetting sensors:', error);
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
    matchWonFlag = false;  // RESET match won flag
    
    console.log('🔄 Match won flag reset - side switches re-enabled');
    
    const winnerDisplay = document.getElementById('winnerDisplay');
    if (winnerDisplay) {
        winnerDisplay.style.display = 'none';
        const stage1 = document.getElementById('stage1');
        const stage2 = document.getElementById('stage2');
        if (stage1) {
            stage1.style.display = 'flex';
            stage1.classList.remove('fade-out');
        }
        if (stage2) stage2.style.display = 'none';
    }
    
    const modeScreen = document.getElementById('modeSelectionScreen');
    if (modeScreen) {
        modeScreen.classList.remove('active');
        modeScreen.style.display = 'none';
    }
    
    const scoreboard = document.querySelector('.scoreboard');
    if (scoreboard) {
        scoreboard.classList.remove('hidden');
    }
    
    updateDisplay();
    
    splashDismissed = false;
    const splashScreen = document.getElementById('splashScreen');
    if (splashScreen) {
        splashScreen.classList.add('active');
        console.log('Match and mode reset complete - splash screen displayed');
    }
}

// ===== TOAST NOTIFICATIONS =====
function showToast(action, team, gameState) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const teamName = team === 'black' ? 'BLACK' : 'YELLOW';
    let icon = '⚪';
    let title = 'POINT SCORED';
    let message = `${teamName} team scored!`;
    let toastType = 'toast-point';
    
    if (action === 'game') {
        icon = '🎾';
        title = 'GAME WON';
        message = `${teamName} wins the game! ${gameState.game1}-${gameState.game2}`;
        toastType = 'toast-game';
    } else if (action === 'set') {
        icon = '🏆';
        title = 'SET WON';
        message = `${teamName} wins the set! Sets ${gameState.set1}-${gameState.set2}`;
        toastType = 'toast-set';
    } else if (action === 'match') {
        icon = '👑';
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
    
    container.appendChild(toast);
    
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

// ===== SETUP CLICKABLE TEAMS =====
function setupClickableTeams() {
    const blackTeam = document.querySelector('.team-section.black-team');
    const yellowTeam = document.querySelector('.team-section.yellow-team');
    
    if (blackTeam) {
        blackTeam.style.cursor = 'pointer';
        blackTeam.addEventListener('click', function(e) {
            if (e.target.closest('.logoClick') || e.target.closest('.controlPanel')) return;
            
            const winnerDisplay = document.getElementById('winnerDisplay');
            if (winnerDisplay && winnerDisplay.style.display === 'flex') {
                clearWinnerTimeout();
                resetMatchAndGoToSplash();
                return;
            }
            
            const splashScreen = document.getElementById('splashScreen');
            if (splashScreen && splashScreen.classList.contains('active')) {
                dismissSplash();
                return;
            }
            
            const modeScreen = document.getElementById('modeSelectionScreen');
            if (modeScreen && modeScreen.style.display === 'flex') {
                selectMode('basic');
                return;
            }
            
            if (isScoreboardActive) {
                addPointManual('black');
            }
        });
    }
    
    if (yellowTeam) {
        yellowTeam.style.cursor = 'pointer';
        yellowTeam.addEventListener('click', function(e) {
            if (e.target.closest('.controlPanel')) return;
            
            const winnerDisplay = document.getElementById('winnerDisplay');
            if (winnerDisplay && winnerDisplay.style.display === 'flex') {
                clearWinnerTimeout();
                resetMatchAndGoToSplash();
                return;
            }
            
            const splashScreen = document.getElementById('splashScreen');
            if (splashScreen && splashScreen.classList.contains('active')) {
                dismissSplash();
                return;
            }
            
            const modeScreen = document.getElementById('modeSelectionScreen');
            if (modeScreen && modeScreen.style.display === 'flex') {
                selectMode('basic');
                return;
            }
            
            if (isScoreboardActive) {
                addPointManual('yellow');
            }
        });
    }
}

// ===== LOGO SETUP =====
function setupLogo() {
    const logo = document.getElementById('logoClick');
    const logoImg = document.getElementById('logoImg');
    const controlPanel = document.getElementById('controlPanel');
    
    if (logoImg) {
        logoImg.onload = function() {
            if (logo) {
                logo.classList.remove('no-image');
            }
        };
        
        logoImg.onerror = function() {
            if (logo) {
                logo.classList.add('no-image');
            }
        };
        
        if (logoImg.complete) {
            if (logoImg.naturalWidth > 0) {
                logoImg.onload();
            } else {
                logoImg.onerror();
            }
        }
    }
    
    if (logo) {
        logo.addEventListener('click', function(e) {
            e.stopPropagation();
            if (controlPanel) {
                if (controlPanel.style.display === 'none' || !controlPanel.style.display) {
                    controlPanel.style.display = 'flex';
                } else {
                    controlPanel.style.display = 'none';
                }
            }
        });
    }
}

// ===== GAME STATE UPDATE =====
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
            return [blackGames, yellowGames];
        });
    }
}

function updateDisplay() {
    const scoreBlack = document.getElementById('scoreBlack');
    const scoreYellow = document.getElementById('scoreYellow');
    const gamesBlack = document.getElementById('gamesBlack');
    const gamesYellow = document.getElementById('gamesYellow');
    const setsBlackEl = document.getElementById('setsBlack');
    const setsYellowEl = document.getElementById('setsYellow');
    
    if (scoreBlack) scoreBlack.textContent = score1;
    if (scoreYellow) scoreYellow.textContent = score2;
    if (gamesBlack) gamesBlack.textContent = games1;
    if (gamesYellow) gamesYellow.textContent = games2;
    if (setsBlackEl) setsBlackEl.textContent = sets1;
    if (setsYellowEl) setsYellowEl.textContent = sets2;
}

// ===== MANUAL POINT ADDITION =====
async function addPointManual(team) {
    try {
        const response = await fetch(`${API_BASE}/addpoint`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ team: team })
        });
        const data = await response.json();
        if (data.success) {
            showClickFeedback(team);
        } else {
            alert(data.error);
        }
    } catch (error) {
        alert('Network error: ' + error.message);
    }
}

async function subtractPoint(team) {
    try {
        const response = await fetch(`${API_BASE}/subtractpoint`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ team: team })
        });
        const data = await response.json();
        if (!data.success) {
            alert(data.error);
        }
    } catch (error) {
        alert('Network error: ' + error.message);
    }
}

// ===== CLICK FEEDBACK =====
function showClickFeedback(team) {
    const feedback = document.getElementById(team === 'black' ? 'clickFeedbackBlack' : 'clickFeedbackYellow');
    if (feedback) {
        feedback.style.animation = 'none';
        setTimeout(() => {
            feedback.style.animation = 'feedbackPulse 0.8s ease-in-out';
        }, 10);
    }
}

// ===== 2-STAGE WINNER DISPLAY =====
async function fetchMatchDataAndDisplay() {
    try {
        const response = await fetch(`${API_BASE}/getmatchdata`);
        const data = await response.json();
        if (data.success && data.matchdata) {
            displayWinnerWithData(data.matchdata);
        }
    } catch (error) {
        console.error('Error fetching match data:', error);
    }
}

function displayWinner(data) {
    if (data.matchdata) {
        displayWinnerWithData(data.matchdata);
    }
}

function displayWinnerWithData(matchData) {
    const winnerDisplay = document.getElementById('winnerDisplay');
    const stage1 = document.getElementById('stage1');
    const stage2 = document.getElementById('stage2');
    const winnerTeamNameStage1 = document.getElementById('winnerTeamNameStage1');
    const winnerTeamNameStage2 = document.getElementById('winnerTeamNameStage2');
    const finalSetsScore = document.getElementById('finalSetsScore');
    const matchDuration = document.getElementById('matchDuration');
    const setsTableBody = document.getElementById('setsTableBody');
    
    // SET MATCH WON FLAG - prevents side switch notifications
    matchWonFlag = true;
    console.log('🏆 Match won flag set - side switches disabled');
    
    // Clear any existing timeout
    clearWinnerTimeout();

    // === STAGE 1: Show trophy + title + winner name ===
    if (winnerTeamNameStage1) {
        winnerTeamNameStage1.textContent = matchData.winnername;
        winnerTeamNameStage1.className = 'winner-team-name ' + matchData.winnerteam;
    }

    // Populate Stage 2 data (hidden for now)
    if (winnerTeamNameStage2) {
        winnerTeamNameStage2.textContent = matchData.winnername;
        winnerTeamNameStage2.className = 'winner-team-name-small ' + matchData.winnerteam;
    }
    
    if (finalSetsScore) finalSetsScore.textContent = matchData.finalsetsscore;
    if (matchDuration) matchDuration.textContent = matchData.matchduration;
    
    if (setsTableBody && matchData.setsbreakdown) {
        let tableHTML = '';
        matchData.setsbreakdown.forEach(set => {
            const blackClass = set.setwinner === 'black' ? 'winner-set' : '';
            const yellowClass = set.setwinner === 'yellow' ? 'winner-set' : '';
            tableHTML += `
                <tr>
                    <td>Set ${set.setnumber}</td>
                    <td class="${blackClass}">${set.blackgames}</td>
                    <td class="${yellowClass}">${set.yellowgames}</td>
                    <td class="team-column">${set.setwinner.toUpperCase()}</td>
                </tr>
            `;
        });
        setsTableBody.innerHTML = tableHTML;
    }

    // Show Stage 1
    if (stage1) {
        stage1.style.display = 'flex';
        stage1.classList.remove('fade-out');
    }
    if (stage2) stage2.style.display = 'none';
    if (winnerDisplay) {
        winnerDisplay.style.display = 'flex';
        isScoreboardActive = false;
    }

    console.log('🏆 STAGE 1: Showing trophy + winner name (5 seconds)');

    // After 5 seconds, transition to Stage 2
    stageTimeout = setTimeout(() => {
        if (stage1) stage1.classList.add('fade-out');
        
        setTimeout(() => {
            if (stage1) {
                stage1.style.display = 'none';
                stage1.classList.remove('fade-out');
            }
            if (stage2) stage2.style.display = 'flex';
            console.log('📊 STAGE 2: Showing BIGGER stats + table (no overflow)');
        }, 500);
    }, 5000);
}

function calculateMatchDuration() {
    const start = new Date(matchStartTime);
    const end = new Date();
    const diff = end - start;
    const minutes = Math.floor(diff / 60000);
    const seconds = Math.floor((diff % 60000) / 1000);
    return `${minutes}m ${seconds}s`;
}

// ===== MATCH RESET =====
async function resetMatch() {
    await resetMatchAndGoToSplash();
}

async function newMatch() {
    await resetMatchAndGoToSplash();
}

function shareResults() {
    alert('Share functionality coming soon!');
}
