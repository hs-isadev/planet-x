# Optional browser validation

The app itself needs no Node or build step. To rerun development browser checks:

    npm install
    npx playwright install chromium
    npm run test:3d
    npm run test:observed
    npm run test:tour

Run these commands from qa/ with the Python app already running on port 8000. They use real services and can take several minutes. The observed check requires actual cutouts; the Tour follows every live preset. No production API responses are mocked. Screenshots are written under ../docs/screenshots. Source fixtures in the Python tests are isolated from the served app.
