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
    socket.emit('request_sensor_validation');
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
});

socket.on('match_won', (data) => {
    console.log('🏆 Match won:', data);
    displayWinner(data);
});

socket.on('sensor_validation_result', (data) => {
    console.log('🔍 Sensor validation result:', data);
    handleSensorValidation(data);
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

const API_BASE = "http://127.0.0.1:5000";

// =================================================================================================
// SENSOR VALIDATION HANDLING
// =================================================================================================

function handleSensorValidation(validation) {
    if (validation.status === 'valid') {
        showWelcomeToast();
    } else if (validation.status === 'error') {
        showErrorToast(validation.error_message);
    }
}

function showWelcomeToast() {
    const toast = document.getElementById('welcomeToast');
    if (toast) {
        toast.style.display = 'flex';
        toast.classList.add('show');
        
        // Auto-hide after 10 seconds
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.style.display = 'none';
            }, 500);
        }, 10000);
    }
}

function showErrorToast(message) {
    const toast = document.getElementById('errorToast');
    const messageEl = document.getElementById('errorMessage');
    
    if (toast && messageEl) {
        messageEl.textContent = message || 'ERROR 1: Restart the SUMMA';
        toast.style.display = 'flex';
        toast.classList.add('show');
        
        // Error toast stays visible until manually closed or page reload
    }
}

function closeErrorToast() {
    const toast = document.getElementById('errorToast');
    if (toast) {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.style.display = 'none';
        }, 500);
    }
}

// =================================================================================================
// INITIALIZATION
// =================================================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('🏓 Padel Scoreboard Initialized');
    
    setupLogo();
    updateTime();
    setInterval(updateTime, 1000);
    
    // Setup clickable team sections
    setupClickableTeams();
    
    // Setup error toast close button
    const closeBtn = document.getElementById('closeErrorToast');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeErrorToast);
    }
});

// =================================================================================================
// SETUP CLICKABLE TEAMS
// =================================================================================================

function setupClickableTeams() {
    // Select teams by their class names since IDs are not used in HTML
    const blackTeam = document.querySelector('.team-section.black-team');
    const yellowTeam = document.querySelector('.team-section.yellow-team');
    
    if (blackTeam) {
        blackTeam.style.cursor = 'pointer';
        blackTeam.addEventListener('click', function(e) {
            // Prevent triggering if clicking logo or control panel
            if (e.target.closest('#logoClick') || e.target.closest('#controlPanel')) {
                return;
            }
            console.log('👆 Black team clicked');
            addPointManual('black');
        });
        console.log('✅ Black team click listener added');
    } else {
        console.error('❌ Black team element not found!');
    }
    
    if (yellowTeam) {
        yellowTeam.style.cursor = 'pointer';
        yellowTeam.addEventListener('click', function(e) {
            // Prevent triggering if clicking control panel
            if (e.target.closest('#controlPanel')) {
                return;
            }
            console.log('👆 Yellow team clicked');
            addPointManual('yellow');
        });
        console.log('✅ Yellow team click listener added');
    } else {
        console.error('❌ Yellow team element not found!');
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
            e.stopPropagation(); // Prevent team click event
            
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
            const winnerClass = set.set_winner === 'black' ? 'winner-set' : '';
            const winnerClass2 = set.set_winner === 'yellow' ? 'winner-set' : '';
            
            tableHTML += `
                <tr>
                    <td class="team-column black">Set ${set.set_number}</td>
                    <td class="${winnerClass}">${set.black_games}</td>
                    <td class="${winnerClass2}">${set.yellow_games}</td>
                </tr>
            `;
        });
        setsTableBody.innerHTML = tableHTML;
    }
    
    if (winnerDisplay) {
        winnerDisplay.style.display = 'flex';
        winnerDisplay.classList.add('show');
    }
}

async function startNewMatch() {
    try {
        await fetch(`${API_BASE}/reset_match`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const winnerDisplay = document.getElementById('winnerDisplay');
        if (winnerDisplay) {
            winnerDisplay.classList.remove('show');
            setTimeout(() => {
                winnerDisplay.style.display = 'none';
            }, 500);
        }
        
        console.log('🔄 New match started');
    } catch (error) {
        console.error('❌ Error starting new match:', error);
    }
}

function shareMatch() {
    console.log('📤 Share match clicked');
    alert('Match sharing feature coming soon!');
}

// =================================================================================================
// CONTROL PANEL FUNCTIONS
// =================================================================================================

async function addBlackPoint() {
    await addPointManual('black');
}

async function addYellowPoint() {
    await addPointManual('yellow');
}

async function resetMatch() {
    if (confirm('Are you sure you want to reset the match?')) {
        await startNewMatch();
    }
}
