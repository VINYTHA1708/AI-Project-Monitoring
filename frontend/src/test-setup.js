// Ensure IS_REACT_ACT_ENVIRONMENT is set before @testing-library/react loads.
// Required for vitest v5 + @testing-library/react v16 compatibility.
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
