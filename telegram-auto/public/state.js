// state.js
const STATE_KEY = 'tg_state';

// Default State
let state = {
    refreshEnabled: false,
    config: JSON.parse(localStorage.getItem('tg_forwarder_config')) || null
};

// Load state from localStorage on script load
const savedState = localStorage.getItem(STATE_KEY);
if (savedState) {
    state = { ...state, ...JSON.parse(savedState) };
}

/**
 * Updates the state and saves to localStorage
 * @param {Object} newState 
 */
function setState(newState) {
    state = { ...state, ...newState };
    localStorage.setItem(STATE_KEY, JSON.stringify(state));
    
    // Dispatch a custom event so the UI can react to changes
    window.dispatchEvent(new CustomEvent('stateUpdate', { detail: state }));
}

function getState() {
    return state;
}

// Export functions to window for global access
window.setState = setState;
window.getState = getState;