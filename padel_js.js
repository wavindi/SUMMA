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
let gameMode = null; // 'basic', 'competition', or null
let isScoreboardActive = false; // Track if scoreboard is ready for scoring

// Mode detection variables
let pendingSensorEvents = []; // Store recent sensor events
const DUAL_SENSOR_WINDOW = 800; // 800ms window to detect both sensors firing
const API_BASE = "http://127.0.0.1:5000";

// =================================================================================================
// SENSOR INPUT HANDLER WITH MODE DETECTION - MODIFIED FOR NEW FLOW
// =================================================================================================
function handleSensorInput(data) {
  const currentTime = Date.now();
  
  // STATE 1: Winner screen is showing - reset match
  const winnerDisplay = document.getElementById('winnerDisplay');
  if (winnerDisplay && winnerDisplay.style.display === 'flex') {
    console.log('🏆 Winner screen visible - sensor input detected, resetting match and going to splash');
    clearWinnerTimeout();
    resetMatchAndGoToSplash();
    return;
  }
  
  // STATE 2: Splash screen is showing - ONLY dismiss on "addpoint" action
  const splashScreen = document.getElementById('splashScreen');
  if (splashScreen && splashScreen.classList.contains('active')) {
    if (data.action === 'addpoint') {
      console.log('✨ Splash screen active - addpoint detected, going to GAME MODE screen');
      dismissSplash(); // This now goes directly to game mode screen
    } else {
      console.log('⏸️ Splash screen active - ignoring non-addpoint action:', data.action);
    }
    return;
  }
  
  // STATE 3: Mode selection screen (game mode screen) - handle addpoint/subtractpoint
  const modeScreen = document.getElementById('modeSelectionScreen');
  if (modeScreen && modeScreen.style.display === 'flex') {
    console.log('🎮 Game mode screen active - handling sensor input');
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
    showClickFeedback(data.team);
    showToast(data.action, data.team, data.gamestate);
  }
}

// =================================================================================================
// MODE DETECTION LOGIC - SIMPLIFIED (no longer needed for sensor detection)
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
  
  // Splash will stay until first "addpoint" action
  
  setupLogo();
  // Start match duration timer
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
  // Auto-dismiss handlers (for manual click/touch if needed)
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
    splashScreen.classList.remove('active');
    
    // CRITICAL CHANGE: Go DIRECTLY to game mode screen (no scoring until mode selected)
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
    console.log('🎮 GAME MODE screen shown - ready for addpoint (BASIC) / subtractpoint (COMPETITION)');
  }
}

async function selectMode(mode) {
  console.log(`🎯 Mode selected: ${mode} - activating scoreboard`);
  
  // Set game mode
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
      console.log('✅ ✅ SCORECARD NOW ACTIVE - points will count from here');
    }, 500);
  }
  
  // Reset and start match timer
  matchStartTime = Date.now();
  console.log('📊 Scoreboard ready - match timer started');
}

// =================================================================================================
// MATCH DURATION TIMER (REPLACES CLOCK)
// =================================================================================================
function updateMatchDuration() {
  const now = Date.now();
  const elapsed = now - matchStartTime;
  
  // Convert to minutes and seconds
  const totalSeconds = Math.floor(elapsed / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  
  // Format as MM:SS
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
  
  // 2. Reset game mode on backend (set to null or empty)
  try {
    const modeResponse = await fetch(`${API_BASE}/setgamemode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
  
  // 3. Reset local variables
  score1 = 0; score2 = 0;
  games1 = 0; games2 = 0;
  sets1 = 0; sets2 = 0;
  matchWon = false;
  winnerData = null;
  setsHistory = [];
  matchStartTime = Date.now();
  gameMode = null; // Reset game mode
  isScoreboardActive = false; // Deactivate scoreboard
  pendingSensorEvents = []; // Clear pending events
  
  // 4. Hide winner display
  const winnerDisplay = document.getElementById('winnerDisplay');
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
    <div class="toast-close"></div>
  `;
  
  container.appendChild(toast);
  
  // Close button
  const closeBtn = toast.querySelector('.toast-close');
  closeBtn.addEventListener('click', () => removeToast(toast));
  
  // Auto-remove after duration based on type
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
  const blackTeam = document.querySelector('.team-section.black-team');
  const yellowTeam = document.querySelector('.team-section.yellow-team');
  
  if (blackTeam) {
    blackTeam.style.cursor = 'pointer';
    blackTeam.addEventListener('click', function(e) {
      if (e.target.closest('#logoClick') || e.target.closest('#controlPanel')) return;
      
      // If winner screen is showing, reset match and go to splash
      const winnerDisplay = document.getElementById('winnerDisplay');
      if (winnerDisplay && winnerDisplay.style.display === 'flex') {
        console.log('Winner screen visible - black side clicked, resetting match and going to splash');
        clearWinnerTimeout();
        resetMatchAndGoToSplash();
        return;
      }
      
      // If splash is showing, dismiss it (go to game mode)
      const splashScreen = document.getElementById('splashScreen');
      if (splashScreen && splashScreen.classList.contains('active')) {
        console.log('Splash active - dismissing (go to game mode)');
        dismissSplash();
        return;
      }
      
      // If game mode screen is showing, manually select BASIC mode
      const modeScreen = document.getElementById('modeSelectionScreen');
      if (modeScreen && modeScreen.style.display === 'flex') {
        console.log('Black team clicked on game mode screen - selecting BASIC mode');
        selectMode('basic');
        return;
      }
      
      // If scoreboard is active, add point via control panel
      if (isScoreboardActive) {
        console.log('Black team clicked - addPointManual(black)');
        addPointManual('black');
      }
    });
    console.log('Black team click listener added');
  }
  
  if (yellowTeam) {
    yellowTeam.style.cursor = 'pointer';
    yellowTeam.addEventListener('click', function(e) {
      if (e.target.closest('#controlPanel')) return;
      
      // If winner screen is showing, reset match and go to splash
      const winnerDisplay = document.getElementById('winnerDisplay');
      if (winnerDisplay && winnerDisplay.style.display === 'flex') {
        console.log('Winner screen visible - yellow side clicked, resetting match and going to splash');
        clearWinnerTimeout();
        resetMatchAndGoToSplash();
        return;
      }
      
      // If splash is showing, dismiss it (go to game mode)
      const splashScreen = document.getElementById('splashScreen');
      if (splashScreen && splashScreen.classList.contains('active')) {
        console.log('Splash active - dismissing (go to game mode)');
        dismissSplash();
        return;
      }
      
      // If game mode screen is showing, manually select BASIC mode
      const modeScreen = document.getElementById('modeSelectionScreen');
      if (modeScreen && modeScreen.style.display === 'flex') {
        console.log('Yellow team clicked on game mode screen - selecting BASIC mode');
        selectMode('basic');
        return;
      }
      
      // If scoreboard is active, add point via control panel
      if (isScoreboardActive) {
        console.log('Yellow team clicked - addPointManual(yellow)');
        addPointManual('yellow');
      }
    });
    console.log('Yellow team click listener added');
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
      console.log('Logo image loaded');
      if (logo) logo.classList.remove('no-image');
    };
    logoImg.onerror = function() {
      console.log('Logo image failed, using fallback');
      if (logo) logo.classList.add('no-image');
    };
    // Handle already loaded image
    if (logoImg.complete && logoImg.naturalWidth === 0) {
      logoImg.onerror();
    } else if (logoImg.complete) {
      logoImg.onload();
    }
  }
  
  if (logo) {
    logo.addEventListener('click', function(e) {
      e.stopPropagation();
      if (controlPanel) {
        if (controlPanel.style.display === 'none' || !controlPanel.style.display) {
          controlPanel.style.display = 'flex';
          console.log('Controls shown');
        } else {
          controlPanel.style.display = 'none';
          console.log('Controls hidden');
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
  
  console.log(`Display updated - Score: ${score1}-${score2} Games: ${games1}-${games2} Sets: ${sets1}-${sets2}`);
}

// =================================================================================================
// MANUAL POINT ADDITION
// =================================================================================================
async function addPointManual(team) {
  console.log(`Adding point to team: ${team}`);
  try {
    const response = await fetch(`${API_BASE}/addpoint`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team: team })
    });
    const data = await response.json();
    if (data.success) {
      console.log('Point added successfully');
      showClickFeedback(team);
    } else {
      console.error('Failed to add point:', data.error);
      alert(data.error);
    }
  } catch (error) {
    console.error('Error adding point:', error);
    alert('Network error: ' + error.message);
  }
}

async function subtractPoint(team) {
  console.log(`Subtracting point from team: ${team}`);
  try {
    const response = await fetch(`${API_BASE}/subtractpoint`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team: team })
    });
    const data = await response.json();
    if (data.success) {
      console.log('Point subtracted successfully');
    } else {
      console.error('Failed to subtract point:', data.error);
      alert(data.error);
    }
  } catch (error) {
    console.error('Error subtracting point:', error);
    alert('Network error: ' + error.message);
  }
}

// =================================================================================================
// CLICK FEEDBACK
// =================================================================================================
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
  console.log('Displaying winner:', matchData);
  
  const winnerDisplay = document.getElementById('winnerDisplay');
  const winnerTeamName = document.getElementById('winnerTeamName');
  const finalSetsScore = document.getElementById('finalSetsScore');
  const matchDuration = document.getElementById('matchDuration');
  const setsTableBody = document.getElementById('setsTableBody');
  
  if (winnerTeamName) {
    winnerTeamName.textContent = matchData.winnername;
    winnerTeamName.className = `winner-team-name ${matchData.winnerteam}`;
  }
  
  if (finalSetsScore) {
    finalSetsScore.textContent = matchData.finalsetsscore;
  }
  
  if (matchDuration) {
    matchDuration.textContent = matchData.matchduration;
  }
  
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
  
  if (winnerDisplay) {
    winnerDisplay.style.display = 'flex';
  }
  
  // Deactivate scoreboard when winner is shown
  isScoreboardActive = false;
  
  // Auto-dismiss after 30 seconds - reset match and go to splash
  clearWinnerTimeout();
  winnerDismissTimeout = setTimeout(() => {
    console.log('Winner screen auto-dismiss (30s) - resetting match and going to splash...');
    resetMatchAndGoToSplash();
  }, 30000);
  
  console.log('Winner screen displayed with 30s auto-dismiss');
}

// =================================================================================================
// MATCH RESET
// =================================================================================================
async function resetMatch() {
  console.log('Reset button clicked - resetting match, mode, and going to splash...');
  await resetMatchAndGoToSplash();
}

// Update newMatch function to also reset and go to splash
async function newMatch() {
  console.log('New match button clicked - resetting match, mode, and going to splash...');
  await resetMatchAndGoToSplash();
}

function shareResults() {
  alert('Share functionality coming soon!');
}
