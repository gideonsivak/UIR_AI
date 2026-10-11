const CURRENT_USER_ID = 'gideonPlantCurrentUserId';
// Legacy browser records are deliberately left untouched; backend JSON is now the source of truth.
export const getCurrentUserId = () => localStorage.getItem(CURRENT_USER_ID);
export const setCurrentUserId = id => localStorage.setItem(CURRENT_USER_ID, id);
export const clearCurrentUserId = () => localStorage.removeItem(CURRENT_USER_ID);
