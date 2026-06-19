# JobLens Web

React + Vite front-end for `POST /analyze`.

## Local dev

```bash
cd web
cp .env.example .env   # optional — default is production EC2 IP
npm install
npm run dev
```

Open http://localhost:5173

## Production API

Default: `http://3.128.164.130:8000`  
AWS hostname: `http://ec2-3-128-164-130.us-east-2.compute.amazonaws.com:8000`

## Lovable

See **[docs/LOVABLE.md](../docs/LOVABLE.md)** for step-by-step setup.
