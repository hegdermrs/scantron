# Scantron OMR Frontend

Simple frontend for students to:

- upload an OMR sheet image
- take a photo of the sheet using the device camera
- preview the image before submission
- send the image to an n8n webhook configured by the app

## Files

- `index.html` - app structure
- `styles.css` - UI styling
- `script.js` - upload, camera, preview, and webhook submission logic
- `config.js` - local webhook configuration used by the frontend
- `config.example.js` - example config template

## How It Sends Data

The frontend makes a `POST` request to your n8n webhook using `multipart/form-data`.

Fields sent:

- `file`
- `source`
- `submittedAt`

## Webhook Configuration

Set your webhook in `config.js`:

```js
window.APP_CONFIG = {
  webhookUrl: "https://your-n8n-domain/webhook/omr-upload",
};
```

Important:

- this keeps the webhook out of the student form
- but it is still not truly secret, because any URL used directly by frontend JavaScript can be seen in the browser
- if you want the n8n webhook to be truly internal/private, use a small backend or proxy endpoint and let the frontend call that instead

## n8n Notes

In n8n, your webhook should:

1. accept `POST`
2. allow binary/file uploads
3. return CORS headers if this frontend is hosted on a different domain

Typical CORS headers on the webhook response:

- `Access-Control-Allow-Origin: *`
- `Access-Control-Allow-Methods: POST, OPTIONS`

## Local Testing

For camera access, open the app over `https` or `localhost`. Browsers usually block camera access on plain `file://` pages.

You can serve it with any static server. For example:

```powershell
python -m http.server 8080
```

Then open `http://localhost:8080`.
