// This file contains the javascript that is run when the notebook is loaded.
// It contains some requirejs configuration and the `load_ipython_extension`
// which is required for any notebook extension.

// Configure requirejs
if (window.require) {
  window.require.config({
    map: {
      "*" : {
        "esper_jupyter": "nbextensions/esper_jupyter/jupyter",
      }
    }
  });
}

// Export the required load_ipython_extension
export function load_ipython_extension () {
  let link = document.createElement('link');
  link.setAttribute('rel', 'stylesheet');
  link.type ='text/css';
  link.href = '/nbextensions/esper_jupyter/styles.css';
  document.head.appendChild(link);
}
