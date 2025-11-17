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

const API_BASE = "http://127.0.0.1:5000";

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
            tableHTML += `
                <tr>
                    <td>Set ${set.set_number}</td>
                    <td class="${set.set_winner === 'black' ? 'winner-set' : ''}">${set.black_games}</td>
                    <td class="${set.set_winner === 'yellow' ? 'winner-set' : ''}">${set.yellow_games}</td>
                    <td class="team-column ${set.set_winner}">
                        ${set.set_winner === 'black' ? 'BLACK TEAM' : 'YELLOW TEAM'}
                    </td>
                </tr>`;
        });
        setsTableBody.innerHTML = tableHTML;
    }

    if (winnerDisplay) winnerDisplay.style.display = 'flex';
    
    markMatchDisplayed();
}

async function markMatchDisplayed() {
    try {
        await fetch(`${API_BASE}/mark_match_displayed`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wipe_immediately: true })
        });
        console.log('✅ Match marked as displayed');
    } catch (error) {
        console.error('❌ Error marking match:', error);
    }
}

// =================================================================================================
// MATCH ACTIONS (NEW MATCH, RESET, SHARE)
// =================================================================================================

function newMatch() {
    resetMatch();
}

async function resetMatch() {
    if (!confirm("Start a new match? This will reset all scores.")) {
        return;
    }

    console.log('🔄 Resetting match...');
    
    try {
        const response = await fetch(`${API_BASE}/reset_match`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            console.log('✅ Match reset successfully');
            
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

            const winnerDisplay = document.getElementById('winnerDisplay');
            if (winnerDisplay) winnerDisplay.style.display = 'none';
            
            updateDisplay();
        } else {
            console.error('❌ Failed to reset match');
            alert('Failed to reset match.');
        }
    } catch (error) {
        console.error('❌ Error resetting match:', error);
        alert('Network error: ' + error.message);
    }
}

function shareResults() {
    if (!winnerData) return;
    
    const shareText = `${winnerData.team_name} wins! Final Score: ${winnerData.final_sets}.`;
    
    if (navigator.share) {
        navigator.share({
            title: 'Padel Match Results',
            text: shareText
        }).catch(err => console.log('❌ Error sharing:', err));
    } else {
        navigator.clipboard.writeText(shareText).then(() => {
            alert('Results copied to clipboard!');
        });
    }
}

console.log('🏓 Padel Scoreboard Loaded');
console.log('📡 Socket.IO Real-time Updates Enabled');
console.log('🖱️ Click logo to show/hide controls');
console.log('👆 Click team sections to add points');
