# FREE Deployment Guide (Vercel + Railway)

## ✅ What You Get (FREE)
- **Frontend:** Unlimited free hosting on Vercel
- **Backend:** Free tier on Railway (includes $5/month free credits)
- **Custom Domain:** Free .railway.app or connect your own

---

## STEP 1: Prepare GitHub Repository

### 1.1 Create GitHub Account
- Go to https://github.com/signup
- Sign up (free)

### 1.2 Create New Repository
- Click "+" > "New repository"
- Name: `data-analysis-tool`
- **PUBLIC** (important for free deployment)
- Click "Create repository"

### 1.3 Push Your Code to GitHub

**Open PowerShell in your project folder:**
```powershell
cd "D:\Data analysis tool"
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/data-analysis-tool.git
git push -u origin main
```

⚠️ Replace `YOUR_USERNAME` with your actual GitHub username

---

## STEP 2: Deploy Backend on Railway (FREE)

### 2.1 Create Railway Account
- Go to https://railway.app
- Click "Sign Up"
- Sign up with GitHub (easiest)

### 2.2 Create New Project
- Click "Create New Project"
- Select "Deploy from GitHub repo"
- Choose your `data-analysis-tool` repository
- Click "Deploy"

### 2.3 Add Environment Variables
In Railway dashboard:
1. Go to your project
2. Click "Variables" tab
3. Add these secrets:

```
GEMINI_API_KEY=AIzaSyCky04G-nmLYUi6leY4Nl_aVhHOnQltPfM
FIREBASE_CREDENTIALS_PATH=./firebase-key.json
PORT=5000
```

### 2.4 Add Firebase Key (Optional)
If you need Firebase:
1. Create a new variable: `FIREBASE_CREDENTIALS`
2. Copy the ENTIRE contents of `firebase-key.json`
3. Paste it as the value (keep it as JSON string)

⚠️ **OR:** Skip Firebase for now - app works without it

### 2.5 Get Your Backend URL
- Railway will auto-generate: `https://yourdomain.railway.app`
- Copy this URL (you'll need it for frontend)

---

## STEP 3: Deploy Frontend on Vercel (FREE)

### 3.1 Create Vercel Account
- Go to https://vercel.com/signup
- Sign up with GitHub (easiest)

### 3.2 Import Project
- Click "Import Project"
- Select your GitHub repo
- Click "Import"

### 3.3 Configure Build Settings
**Framework:** Vite  
**Root Directory:** `Updated Front_End`  
**Build Command:** `npm run build`  
**Output Directory:** `dist`

### 3.4 Add Environment Variables
In Vercel:
1. Go to "Settings" > "Environment Variables"
2. Add:

```
VITE_API_URL=https://yourdomain.railway.app
```

Replace with your actual Railway URL from Step 2.5

### 3.5 Deploy
- Click "Deploy"
- Wait 2-5 minutes
- Your app is LIVE at `yourproject.vercel.app` ✅

---

## STEP 4: Update CORS in Backend (Important!)

Edit `main.py` Line 62:

**BEFORE:**
```python
CORS(app)  # Enable CORS for all routes
```

**AFTER:**
```python
CORS(app, resources={
    r"/api/*": {
        "origins": ["https://yourproject.vercel.app"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})
```

Then push to GitHub:
```powershell
git add main.py
git commit -m "Update CORS for Vercel frontend"
git push
```

Railway auto-redeploys!

---

## STEP 5: Update Frontend API URL

Edit `Updated Front_End\src\components\SelectDataSource.tsx`

Find all API calls and update:
```
http://localhost:5000 → https://yourdomain.railway.app
```

Push to GitHub - Vercel auto-redeploys!

---

## ✅ Your App is LIVE!

### Free Tier Limits:
- ✅ Vercel: Unlimited for static sites
- ✅ Railway: $5/month free credits (enough for hobby projects)
- ✅ Gemini API: First 50 requests/day free

### Custom Domain (Optional)
- Vercel: Add under "Settings" > "Domains"
- Railway: Under "Settings" > "Custom Domain"

---

## Troubleshooting

### Backend won't deploy?
1. Check Railway logs: Dashboard > Deployments
2. Ensure Python 3.9+ selected
3. Delete `__pycache__` locally, push again

### Frontend shows 404?
1. Check `vite.config.ts` - base path correct?
2. Vercel logs: Deployments tab
3. Clear browser cache (Ctrl+Shift+Del)

### API calls failing?
1. Check CORS settings in `main.py`
2. Verify Railway URL in frontend `.env`
3. Check Railway logs for errors

### Questions?
- Railway docs: https://docs.railway.app
- Vercel docs: https://vercel.com/docs

---

**You now have a FREE production app! 🚀**
