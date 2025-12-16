// ============================================================================
// SOCKET.IO REAL-TIME CONNECTION
// ============================================================================
const socket = io("http://127.0.0.1:5000", {
    transports: ["polling", "websocket"],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 10
});

socket.on("connect", () => {
    console.log("✓ Connected to server via Socket.IO");
    socket.emit("request_gamestate");
});

socket.on("disconnect", () => {
    console.log("✗ Disconnected from server");
});

socket.on("gamestate_update", (data) => {
    console.log("Game state update received:", data);
    updateFromGameState(data);
});

socket.on("point_scored", (data) => {
    console.log("Point scored:", data);
    
    // If winner screen is showing, hide it when point is scored
    const winnerDisplay = document.getElementById("winnerDisplay");
    if (winnerDisplay && winnerDisplay.style.display === "flex") {
        console.log("Winner screen visible - closing on sensor point");
        resetMatchSilent();
        return;
    }
    
    showClickFeedback(data.team);
    showToast(data.action, data.team, data.gamestate);
});

socket.on("match_won", (data) => {
    console.log("Match won:", data);
    displayWinner(data);
});

socket.on("gamemode_confirmed", (data) => {
    if (data.success) {
        console.log(`✓ Game mode confirmed: ${data.mode.toUpperCase()}`);
    } else {
        console.error("✗ Failed to set game mode:", data.error);
    }
});

socket.on("side_switch_required", (data) => {
    console.log("Side switch required:", data);
    showSideSwitchToast(data);
});

// ============================================================================
// GAME VARIABLES
// ============================================================================
let score1 = 0;
let score2 = 0;
let games1 = 0;
let games2 = 0;
let sets1 = 0;
let sets2 = 0;
let time = "19:22";
let matchWon = false;
let winnerData = null;
let setsHistory = [];
let matchStartTime = Date.now();
let splashDismissed = false;
let selectedGameMode = "competition"; // Default mode

const API_BASE = "http://127.0.0.1:5000";

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener("DOMContentLoaded", function() {
    console.log("Padel Scoreboard Initialized");
    
    setupSplashScreen();
    setupLogo();
    updateTime();
    setInterval(updateTime, 1000);
    setupClickableTeams();
    setupWinnerScreenClickDismiss();
});

// ============================================================================
// SPLASH SCREEN
// ============================================================================
function setupSplashScreen() {
    const splashScreen = document.getElementById("splashScreen");
    
    // Dismiss splash and show mode selection
    const dismissSplash = () => {
        if (!splashDismissed) {
            splashDismissed = true;
            splashScreen.classList.remove("active");
            
            // Show mode selection after splash
            setTimeout(() => {
                showModeSelection();
            }, 500);
            
            console.log("Splash screen dismissed");
        }
    };
    
    splashScreen.addEventListener("click", dismissSplash);
    splashScreen.addEventListener("touchstart", dismissSplash);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        if (!splashDismissed) {
            dismissSplash();
        }
    }, 5000);
}

// ============================================================================
// MODE SELECTION SCREEN
// ============================================================================
function showModeSelection() {
    const modeScreen = document.getElementById("modeSelectionScreen");
    if (modeScreen) {
        modeScreen.classList.add("active");
        console.log("Mode selection screen shown");
    }
}

function selectMode(mode) {
    console.log(`Mode selected: ${mode.toUpperCase()}`);
    
    // Store selected mode
    selectedGameMode = mode;
    
    // Send mode to backend via Socket.IO
    socket.emit("set_game_mode", { mode: mode });
    
    // Hide mode selection screen
    const modeScreen = document.getElementById("modeSelectionScreen");
    if (modeScreen) {
        modeScreen.classList.remove("active");
        setTimeout(() => {
            modeScreen.style.display = "none";
        }, 500);
    }
    
    // Show scoreboard (it's already visible in the background)
    console.log("Scoreboard ready");
    
    // Show mode confirmation toast
    showModeConfirmationToast(mode);
}

function showModeConfirmationToast(mode) {
    const modeNames = {
        "basic": "BASIC MODE",
        "competition": "COMPETITION MODE",
        "lock": "LOCK MODE"
    };
    
    const modeDescriptions = {
        "basic": "Swap sides after every game",
        "competition": "Swap sides after odd games (1, 3, 5, 7...)",
        "lock": "Same as Competition (locked)"
    };
    
    showCustomToast(
        "⚙️",
        modeNames[mode] || "GAME MODE",
        modeDescriptions[mode] || "Mode activated",
        "toast-mode",
        4000
    );
}

// ============================================================================
// WINNER SCREEN CLICK TO DISMISS
// ============================================================================
function setupWinnerScreenClickDismiss() {
    const winnerDisplay = document.getElementById("winnerDisplay");
    if (winnerDisplay) {
        winnerDisplay.addEventListener("click", (e) => {
            // Don't close if clicking on buttons
            if (e.target.closest(".action-button")) return;
            
            // Only close if the winner screen is actually visible
            if (winnerDisplay.style.display === "flex") {
                console.log("Winner screen clicked - resetting match");
                resetMatchSilent();
            }
        });
        console.log("Winner screen click-to-dismiss enabled");
    }
}

// ============================================================================
// TOAST NOTIFICATIONS
// ============================================================================
function showToast(action, team, gameState) {
    const container = document.getElementById("toastContainer");
    if (!container) return;
    
    const teamName = team === "black" ? "BLACK" : "YELLOW";
    let icon = "🎾";
    let title = "POINT SCORED";
    let message = `${teamName} team scored!`;
    let toastType = "toast-point";
    
    if (action === "game") {
        icon = "🏆";
        title = "GAME WON";
        message = `${teamName} wins the game! ${gameState.game1}-${gameState.game2}`;
        toastType = "toast-game";
    } else if (action === "set") {
        icon = "⭐";
        title = "SET WON";
        message = `${teamName} wins the set! Sets: ${gameState.set1}-${gameState.set2}`;
        toastType = "toast-set";
    } else if (action === "match") {
        icon = "👑";
        title = "MATCH WON";
        message = `${teamName} wins the match!`;
        toastType = "toast-match";
    }
    
    showCustomToast(icon, title, message, toastType, getDurationForAction(action));
}

function showSideSwitchToast(data) {
    const message = `Total games: ${data.totalgames} | Score: ${data.gamescore} | Sets: ${data.setscore}`;
    showCustomToast("🔄", "CHANGE SIDES", message, "toast-side-switch", 5000);
}

function showCustomToast(icon, title, message, toastType, duration) {
    const container = document.getElementById("toastContainer");
    if (!container) return;
    
    const toast = document.createElement("div");
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
    const closeBtn = toast.querySelector(".toast-close");
    closeBtn.addEventListener("click", () => removeToast(toast));
    
    // Auto-remove after duration
    setTimeout(() => removeToast(toast), duration);
}

function getDurationForAction(action) {
    if (action === "match") return 8000;
    if (action === "set") return 5000;
    if (action === "game") return 4000;
    return 3000;
}

function removeToast(toast) {
    toast.classList.add("toast-out");
    setTimeout(() => {
        if (toast.parentElement) {
            toast.parentElement.removeChild(toast);
        }
    }, 400);
}

// ============================================================================
// SETUP CLICKABLE TEAMS - WITH WINNER SCREEN RESET
// ============================================================================
function setupClickableTeams() {
    const blackTeam = document.querySelector(".team-section.black-team");
    const yellowTeam = document.querySelector(".team-section.yellow-team");
    
    if (blackTeam) {
        blackTeam.style.cursor = "pointer";
        blackTeam.addEventListener("click", (e) => {
            if (e.target.closest("#logoClick") || e.target.closest("#controlPanel")) return;
            
            // If winner screen is showing, reset match instead of adding point
            const winnerDisplay = document.getElementById("winnerDisplay");
            if (winnerDisplay && winnerDisplay.style.display === "flex") {
                console.log("Winner screen visible - resetting match");
                resetMatchSilent();
                return;
            }
            
            console.log("Black team clicked");
            addPointManual("black");
            hideSplashOnFirstPoint();
        });
        console.log("✓ Black team click listener added");
    }
    
    if (yellowTeam) {
        yellowTeam.style.cursor = "pointer";
        yellowTeam.addEventListener("click", (e) => {
            if (e.target.closest("#controlPanel")) return;
            
            // If winner screen is showing, reset match instead of adding point
            const winnerDisplay = document.getElementById("winnerDisplay");
            if (winnerDisplay && winnerDisplay.style.display === "flex") {
                console.log("Winner screen visible - resetting match");
                resetMatchSilent();
                return;
            }
            
            console.log("Yellow team clicked");
            addPointManual("yellow");
            hideSplashOnFirstPoint();
        });
        console.log("✓ Yellow team click listener added");
    }
}

function hideSplashOnFirstPoint() {
    const splashScreen = document.getElementById("splashScreen");
    if (splashScreen && !splashDismissed) {
        splashDismissed = true;
        splashScreen.classList.remove("active");
        console.log("Splash hidden on first point");
    }
}

// ============================================================================
// LOGO SETUP
// ============================================================================
function setupLogo() {
    const logo = document.getElementById("logoClick");
    const logoImg = document.getElementById("logoImg");
    const controlPanel = document.getElementById("controlPanel");
    
    if (logoImg) {
        logoImg.onload = function() {
            console.log("✓ Logo image loaded");
            if (logo) logo.classList.remove("no-image");
        };
        
        logoImg.onerror = function() {
            console.log("✗ Logo image failed, using fallback");
            if (logo) logo.classList.add("no-image");
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
        logo.addEventListener("click", (e) => {
            e.stopPropagation();
            if (controlPanel) {
                if (controlPanel.style.display === "none" || !controlPanel.style.display) {
                    controlPanel.style.display = "flex";
                    console.log("Controls shown");
                } else {
                    controlPanel.style.display = "none";
                    console.log("Controls hidden");
                }
            }
        });
    }
}

// ============================================================================
// TIME UPDATE
// ============================================================================
function updateTime() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    time = `${hours}:${minutes}`;
    
    const timeEl = document.getElementById("timeDisplay");
    if (timeEl) {
        timeEl.textContent = time;
    }
}

// ============================================================================
// GAME STATE UPDATE FROM SOCKET.IO
// ============================================================================
function updateFromGameState(gameState) {
    score1 = gameState.score1;
    score2 = gameState.score2;
    games1 = gameState.game1;
    games2 = gameState.game2;
    sets1 = gameState.set1;
    sets2 = gameState.set2;
    matchWon = gameState.matchwon;
    
    // Update selected game mode if provided
    if (gameState.gamemode) {
        selectedGameMode = gameState.gamemode;
    }
    
    updateDisplay();
    
    if (gameState.matchwon && gameState.winner) {
        winnerData = gameState.winner;
        fetchMatchDataAndDisplay();
    }
    
    if (gameState.sethistory && gameState.sethistory.length > 0) {
        setsHistory = gameState.sethistory.map(setScore => {
            const parts = setScore.split("-");
            const blackGames = parseInt(parts[0].split("(")[0]);
            const yellowGames = parseInt(parts[1].split("(")[0]);
            return [blackGames, yellowGames];
        });
    }
}

function updateDisplay() {
    const scoreBlack = document.getElementById("scoreBlack");
    const scoreYellow = document.getElementById("scoreYellow");
    const gamesBlack = document.getElementById("gamesBlack");
    const gamesYellow = document.getElementById("gamesYellow");
    const setsBlackEl = document.getElementById("setsBlack");
    const setsYellowEl = document.getElementById("setsYellow");
    
    if (scoreBlack) scoreBlack.textContent = score1;
    if (scoreYellow) scoreYellow.textContent = score2;
    if (gamesBlack) gamesBlack.textContent = games1;
    if (gamesYellow) gamesYellow.textContent = games2;
    if (setsBlackEl) setsBlackEl.textContent = sets1;
    if (setsYellowEl) setsYellowEl.textContent = sets2;
    
    console.log(`Display updated - Score: ${score1}-${score2} | Games: ${games1}-${games2} | Sets: ${sets1}-${sets2}`);
}

// ============================================================================
// MANUAL POINT ADDITION (FROM CONTROLS AND TEAM CLICKS)
// ============================================================================
async function addPointManual(team) {
    console.log(`Adding point to team: ${team.toUpperCase()}`);
    try {
        const response = await fetch(`${API_BASE}/addpoint`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ team: team })
        });
        
        const data = await response.json();
        
        if (data.success) {
            console.log("✓ Point added successfully");
            showClickFeedback(team);
        } else {
            console.error("✗ Failed to add point:", data.error);
            alert(data.error);
        }
    } catch (error) {
        console.error("✗ Error adding point:", error);
        alert(`Network error: ${error.message}`);
    }
}

async function subtractPoint(team) {
    console.log(`Subtracting point from team: ${team.toUpperCase()}`);
    try {
        const response = await fetch(`${API_BASE}/subtractpoint`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ team: team })
        });
        
        const data = await response.json();
        
        if (data.success) {
            console.log("✓ Point subtracted successfully");
        } else {
            console.error("✗ Failed to subtract point:", data.error);
            alert(data.error);
        }
    } catch (error) {
        console.error("✗ Error subtracting point:", error);
        alert(`Network error: ${error.message}`);
    }
}

function showClickFeedback(team) {
    const feedback = document.getElementById(team === "black" ? "clickFeedbackBlack" : "clickFeedbackYellow");
    if (feedback) {
        feedback.style.animation = "none";
        setTimeout(() => {
            feedback.style.animation = "feedbackPulse 0.8s ease-in-out";
        }, 10);
    }
}

// ============================================================================
// WINNER DISPLAY
// ============================================================================
async function fetchMatchDataAndDisplay() {
    try {
        const response = await fetch(`${API_BASE}/getmatchdata`);
        const data = await response.json();
        
        if (data.success && data.matchdata) {
            displayWinnerWithData(data.matchdata);
        }
    } catch (error) {
        console.error("✗ Error fetching match data:", error);
    }
}

function displayWinner(data) {
    if (data.matchdata) {
        displayWinnerWithData(data.matchdata);
    }
}

function displayWinnerWithData(matchData) {
    console.log("Displaying winner:", matchData);
    
    const winnerDisplay = document.getElementById("winnerDisplay");
    const winnerTeamName = document.getElementById("winnerTeamName");
    const finalSetsScore = document.getElementById("finalSetsScore");
    const matchDuration = document.getElementById("matchDuration");
    const setsTableBody = document.getElementById("setsTableBody");
    
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
        let tableHTML = "";
        matchData.setsbreakdown.forEach(set => {
            const blackClass = set.setwinner === "black" ? "winner-set" : "";
            const yellowClass = set.setwinner === "yellow" ? "winner-set" : "";
            tableHTML += `
                <tr>
                    <td>Set ${set.setnumber}</td>
                    <td class="${blackClass}">${set.blackgames}</td>
                    <td class="${yellowClass}">${set.yellowgames}</td>
                    <td class="team-column ${set.setwinner}">${set.setwinner.toUpperCase()}</td>
                </tr>
            `;
        });
        setsTableBody.innerHTML = tableHTML;
    }
    
    if (winnerDisplay) {
        winnerDisplay.style.display = "flex";
    }
}

// ============================================================================
// MATCH RESET - SILENT VERSION (NO CONFIRMATION)
// ============================================================================
async function resetMatchSilent() {
    console.log("Resetting match silently...");
    
    try {
        const response = await fetch(`${API_BASE}/resetmatch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        
        const data = await response.json();
        
        if (data.success) {
            console.log("✓ Match reset successfully");
            
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
            
            // Hide winner display
            const winnerDisplay = document.getElementById("winnerDisplay");
            if (winnerDisplay) {
                winnerDisplay.style.display = "none";
            }
            
            // Update scoreboard
            updateDisplay();
            
            console.log("Ready for new match");
        } else {
            console.error("✗ Failed to reset match");
        }
    } catch (error) {
        console.error("✗ Error resetting match:", error);
    }
}

// Keep the original reset function for manual control panel use
async function resetMatch() {
    if (confirm("Reset current match? All scores will be cleared.")) {
        await resetMatchSilent();
    }
}

// Update newMatch function to use silent reset
async function newMatch() {
    await resetMatchSilent();
}

function shareResults() {
    alert("Share functionality coming soon!");
}
