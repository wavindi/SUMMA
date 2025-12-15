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
    socket.emit('request_game_state');
});

socket.on('disconnect', () => {
    console.log('❌ Disconnected from server');
});

socket.on('game_state_update', (data) => {
    console.log('📡 Game state update received:', data);
    updateFromGameState(data);
});

socket.on('point_scored', (data) => {
    console.log('🎯 Point scored:', data);
    showClickFeedback(data.team);
    showToast(data.action, data.team, data.game_state);
});

socket.on('match_won', (data) => {
    console.log('🏆 Match won:', data);
    displayWinner(data);
});

// =================================================================================================
// GAME VARIABLES
// =================================================================================================

let score_1 = 0;
let score_2 = 0;
let games_1 = 0;
let games_2 = 0;
let sets_1 = 0;
let sets_2 = 0;
let time = "19:22";
let matchWon = false;
let winnerData = null;
let setsHistory = [];
let matchStartTime = Date.now();
let splashDismissed = false;

const API_BASE = "http://127.0.0.1:5000";

// =================================================================================================
// INITIALIZATION
// =================================================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('🏓 Padel Scoreboard Initialized');
    
    setupSplashScreen();
    setupLogo();
    updateTime();
    setInterval(updateTime, 1000);
    setupClickableTeams();
});

// =================================================================================================
// SPLASH SCREEN
// =================================================================================================

function setupSplashScreen() {
    const splashScreen = document.getElementById('splashScreen');
    
    // Dismiss splash on any click/touch
    const dismissSplash = () => {
        if (!splashDismissed) {
            splashDismissed = true;
            splashScreen.classList.remove('active');
            console.log('✨ Splash screen dismissed');
        }
    };
    
    splashScreen.addEventListener('click', dismissSplash);
    splashScreen.addEventListener('touchstart', dismissSplash);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        if (!splashDismissed) {
            dismissSplash();
        }
    }, 5000);
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
        message = `${teamName} wins the game! ${gameState.game_1}-${gameState.game_2}`;
        toastType = 'toast-game';
    } else if (action === 'set') {
        icon = '🏅';
        title = 'SET WON';
        message = `${teamName} wins the set! Sets: ${gameState.set_1}-${gameState.set_2}`;
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
    
    container.appendChild(toast);
    
    // Close button
    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => {
        removeToast(toast);
    });
    
    // Auto-remove after duration based on type
    const duration = action === 'match' ? 8000 : action === 'set' ? 5000 : action === 'game' ? 4000 : 3000;
    setTimeout(() => {
        removeToast(toast);
    }, duration);
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
// SETUP CLICKABLE TEAMS - WITH WINNER SCREEN RESET
// =================================================================================================

function setupClickableTeams() {
    const blackTeam = document.querySelector('.team-section.black-team');
    const yellowTeam = document.querySelector('.team-section.yellow-team');
    
    if (blackTeam) {
        blackTeam.style.cursor = 'pointer';
        blackTeam.addEventListener('click', function(e) {
            if (e.target.closest('#logoClick') || e.target.closest('#controlPanel')) {
                return;
            }
            
            // If winner screen is showing, reset match instead of adding point
            const winnerDisplay = document.getElementById('winnerDisplay');
            if (winnerDisplay && winnerDisplay.style.display === 'flex') {
                console.log('👆 Winner screen visible - resetting match');
                resetMatchSilent();
                return;
            }
            
            console.log('👆 Black team clicked');
            addPointManual('black');
            hideSplashOnFirstPoint();
        });
        console.log('✅ Black team click listener added');
    }
    
    if (yellowTeam) {
        yellowTeam.style.cursor = 'pointer';
        yellowTeam.addEventListener('click', function(e) {
            if (e.target.closest('#controlPanel')) {
                return;
            }
            
            // If winner screen is showing, reset match instead of adding point
            const winnerDisplay = document.getElementById('winnerDisplay');
            if (winnerDisplay && winnerDisplay.style.display === 'flex') {
                console.log('👆 Winner screen visible - resetting match');
                resetMatchSilent();
                return;
            }
            
            console.log('👆 Yellow team clicked');
            addPointManual('yellow');
            hideSplashOnFirstPoint();
        });
        console.log('✅ Yellow team click listener added');
    }
}

function hideSplashOnFirstPoint() {
    const splashScreen = document.getElementById('splashScreen');
    if (splashScreen && !splashDismissed) {
        splashDismissed = true;
        splashScreen.classList.remove('active');
        console.log('✨ Splash hidden on first point');
    }
}

// =================================================================================================
// LOGO SETUP
// =================================================================================================

function setupLogo() {
    const logo = document.getElementById('logoClick');
    const logoImg = document.getElementById('logoImg');
    const controlPanel = document.getElementById('controlPanel');
    
    if (logoImg) {
        logoImg.onload = function() {
            console.log('✅ Logo image loaded');
            if (logo) logo.classList.remove('no-image');
        };
        
        logoImg.onerror = function() {
            console.log('⚠️ Logo image failed, using fallback');
            if (logo) logo.classList.add('no-image');
        };
        
        if (logoImg.complete) {
            if (logoImg.naturalWidth === 0) {
                logoImg.onerror();
            } else {
                logoImg.onload();
            }
        }
    }
    
    if (logo) {
        logo.addEventListener('click', function(e) {
            e.stopPropagation();
            if (controlPanel) {
                if (controlPanel.style.display === 'none' || !controlPanel.style.display) {
                    controlPanel.style.display = 'flex';
                    console.log('🎮 Controls shown');
                } else {
                    controlPanel.style.display = 'none';
                    console.log('🎮 Controls hidden');
                }
            }
        });
    }
}

// =================================================================================================
// TIME UPDATE
// =================================================================================================

function updateTime() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    time = `${hours}:${minutes}`;
    
    const timeEl = document.getElementById('timeDisplay');
    if (timeEl) timeEl.textContent = time;
}

// =================================================================================================
// GAME STATE UPDATE FROM SOCKET.IO
// =================================================================================================

function updateFromGameState(gameState) {
    score_1 = gameState.score_1;
    score_2 = gameState.score_2;
    games_1 = gameState.game_1;
    games_2 = gameState.game_2;
    sets_1 = gameState.set_1;
    sets_2 = gameState.set_2;
    matchWon = gameState.match_won;
    
    updateDisplay();
    
    if (gameState.match_won && gameState.winner) {
        winnerData = gameState.winner;
        fetchMatchDataAndDisplay();
    }
    
    if (gameState.set_history && gameState.set_history.length > 0) {
        setsHistory = gameState.set_history.map(setScore => {
            const [blackGames, yellowGames] = setScore.split('-').map(Number);
            return { blackGames, yellowGames };
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
    
    if (scoreBlack) scoreBlack.textContent = score_1;
    if (scoreYellow) scoreYellow.textContent = score_2;
    if (gamesBlack) gamesBlack.textContent = games_1;
    if (gamesYellow) gamesYellow.textContent = games_2;
    if (setsBlackEl) setsBlackEl.textContent = sets_1;
    if (setsYellowEl) setsYellowEl.textContent = sets_2;
    
    console.log(`📊 Display updated - Score: ${score_1}-${score_2} | Games: ${games_1}-${games_2} | Sets: ${sets_1}-${sets_2}`);
}

// =================================================================================================
// MANUAL POINT ADDITION (FROM CONTROLS AND TEAM CLICKS)
// =================================================================================================

async function addPointManual(team) {
    console.log(`➕ Adding point to ${team} team`);
    
    try {
        const response = await fetch(`${API_BASE}/add_point`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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
        const response = await fetch(`${API_BASE}/subtract_point`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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
    const feedback = document.getElementById(team === 'black' ? 'clickFeedbackBlack' : 'clickFeedbackYellow');
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
        const response = await fetch(`${API_BASE}/get_match_data`);
        const data = await response.json();
        
        if (data.success && data.match_data) {
            displayWinnerWithData(data.match_data);
        }
    } catch (error) {
        console.error('❌ Error fetching match data:', error);
    }
}

function displayWinner(data) {
    if (data.match_data) {
        displayWinnerWithData(data.match_data);
    }
}

function displayWinnerWithData(matchData) {
    console.log('🏆 Displaying winner:', matchData);
    
    const winnerDisplay = document.getElementById('winnerDisplay');
    const winnerTeamName = document.getElementById('winnerTeamName');
    const finalSetsScore = document.getElementById('finalSetsScore');
    const matchDuration = document.getElementById('matchDuration');
    const setsTableBody = document.getElementById('setsTableBody');
    
    if (winnerTeamName) {
        winnerTeamName.textContent = matchData.winner_name;
        winnerTeamName.className = 'winner-team-name ' + matchData.winner_team;
    }
    
    if (finalSetsScore) {
        finalSetsScore.textContent = matchData.final_sets_score;
    }
    
    if (matchDuration) {
        matchDuration.textContent = matchData.match_duration;
    }
    
    if (setsTableBody && matchData.sets_breakdown) {
        let tableHTML = '';
        matchData.sets_breakdown.forEach((set) => {
            const blackClass = set.set_winner === 'black' ? 'winner-set' : '';
            const yellowClass = set.set_winner === 'yellow' ? 'winner-set' : '';
            
            tableHTML += `
                <tr>
                    <td>Set ${set.set_number}</td>
                    <td class="${blackClass}">${set.black_games}</td>
                    <td class="${yellowClass}">${set.yellow_games}</td>
                    <td class="team-column ${set.set_winner}">${set.set_winner.toUpperCase()}</td>
                </tr>
            `;
        });
        setsTableBody.innerHTML = tableHTML;
    }
    
    if (winnerDisplay) {
        winnerDisplay.style.display = 'flex';
    }
}

// =================================================================================================
// MATCH RESET - SILENT VERSION (NO CONFIRMATION)
// =================================================================================================

async function resetMatchSilent() {
    console.log('🔄 Resetting match silently...');
    
    try {
        const response = await fetch(`${API_BASE}/reset_match`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            console.log('✅ Match reset successfully');
            
            // Reset local variables
            score_1 = 0;
            score_2 = 0;
            games_1 = 0;
            games_2 = 0;
            sets_1 = 0;
            sets_2 = 0;
            matchWon = false;
            winnerData = null;
            setsHistory = [];
            matchStartTime = Date.now();
            
            // Hide winner display
            const winnerDisplay = document.getElementById('winnerDisplay');
            if (winnerDisplay) {
                winnerDisplay.style.display = 'none';
            }
            
            // Update scoreboard
            updateDisplay();
            
            console.log('🎮 Ready for new match');
        } else {
            console.error('❌ Failed to reset match');
        }
    } catch (error) {
        console.error('❌ Error resetting match:', error);
    }
}

// Keep the original reset function for manual control panel use
async function resetMatch() {
    if (confirm('Reset current match? All scores will be cleared.')) {
        await resetMatchSilent();
    }
}

// Update newMatch function to use silent reset
async function newMatch() {
    await resetMatchSilent();
}

function shareResults() {
    alert('Share functionality coming soon!');
}
