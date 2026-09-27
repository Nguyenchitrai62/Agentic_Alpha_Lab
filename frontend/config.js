// Public frontend settings (no secrets here). The Google client ID is read from the backend (/api/public/config)
// when left empty, so it only has to be set once in the server's .env.
window.APP_CONFIG = {
  apiBaseUrl: ["localhost", "127.0.0.1"].includes(location.hostname)
    ? "http://127.0.0.1:8724"
    : "https://api-crypto.nguyenchitrai.id.vn",
  googleClientId: "",
};
