# AI-Assisted Junk Detection Tool

A simple Python program that detects duplicate and near-duplicate files in a folder.

---

## **What This Program Does**

This tool analyzes files in your `data` folder and:

1. **Finds Exact Duplicates** - Files with the same content (even if names are different)
2. **Finds Near Duplicates** - Files with very similar names
3. **Checks File Sizes** - Filters candidates based on size similarity
4. **Detects Outdated Files** - Finds files not modified in 6 months
5. **AI Verification** (Optional) - Uses Gemini AI to confirm duplicates by analysing metadata
6. **Archives Files Safely** - Moves duplicates and old files to structured archive folders (NEVER deletes)

---

## **NEW: Archive Feature** ✨

The program now includes intelligent file archiving:

- **Safe Archiving**: Files are MOVED (not deleted) to archive folders
- **Smart Selection**: Keeps the best version of each duplicate
- **Preview First**: Shows what will be archived before executing
- **Reversible**: Archived files can be manually restored
- **Storage Savings**: Shows how much space will be freed

Archive Structure:
```
data/
└── archive/
    ├── exact_duplicates/     (identical files)
    ├── near_duplicates/      (similar files)
    └── outdated/             (old files not modified in 6 months)
```

---

## **Project Structure**

```
d:\Data analysis tool\
├── main.py              ← Main program (run this!)
├── .env                 ← Your Gemini API key
├── README.md            ← This file
├── data\                ← Your test files go here
│   ├── file_1.txt
│   ├── file_2.txt
│   └── ... (more files)
└── .venv\               ← Python environment (auto-created)
```

---

## **How to Use**

### **Step 1: Add Your Files**

Put any files you want to check in the `data` folder:
- Images, PDFs, text files, anything!

Example:
```
data/
├── photo1.jpg
├── photo1_backup.jpg
├── document.pdf
└── old_report.xlsx
```

### **Step 2: Run the Program**

Open PowerShell and run:

```powershell
cd "d:\Data analysis tool"
& "D:/Data analysis tool/.venv/Scripts/python.exe" main.py
```

Or simpler - just double-click `main.py` from VS Code!

### **Step 3: Read the Output**

The program prints results for each detection layer:

```
Step 1: Reading all files and creating hashes...
Step 2: Looking for EXACT duplicates (same content)...
[EXACT] Exact Duplicate: file_5.txt <--> file_6.txt

Step 3: Looking for NEAR duplicate candidates (name similarity)...
Step 4: Checking file sizes for near duplicate candidates...
[NEAR] Near Duplicate Candidate: file_1.txt <--> file_10.txt
  Name similarity: 95%
  Size difference: 3.6%
  Status: Strong candidate

Step 5: Gemini AI verification (temporarily disabled - quota limit)...
Step 6: Looking for OUTDATED files (not modified in 6 months)...
[OLD] Outdated File: file_1.txt (last modified: 1095.1 days ago)

SUMMARY:
Total files checked: 13
Exact duplicates found: 3
Near duplicate candidates: 1
Outdated files found: 4
```

---

## **Understanding the Output**

### **[EXACT] Exact Duplicates**
- Same file content, different names
- Detected using hash (MD5 fingerprint)
- Example: `photo.jpg` and `photo_backup.jpg`

### **[NEAR] Near Duplicate Candidates**
- Very similar file names (95%+ match)
- Checked if file sizes are within 20% of each other
- Example: `report_2023.docx` and `report_2023_final.docx`

### **[OLD] Outdated Files**
- Files not modified in 6 months (180 days)
- Helps find old/unused files
- Example: Files from July 2025 (today is January 2026)

---

## **How the Detection Works (Simple Explanation)**

### **Layer 1: Read Files & Create Hash**
- Open each file
- Calculate MD5 hash (a unique fingerprint)
- Store in memory

### **Layer 2: Find Exact Duplicates**
- Compare all file hashes
- If two hashes match → same content = exact duplicate!

### **Layer 3: Find Near Duplicate Candidates**
- Compare file names
- If names are 95%+ similar → potential near duplicate

### **Layer 4: Check File Sizes**
- Get size of each candidate pair
- If sizes within 20% different → "Strong candidate"
- If sizes >20% different → "Weak candidate" (probably not duplicates)

### **Layer 5: Gemini AI Verification (Optional)**
- Send metadata to Gemini AI
- AI says "YES" or "NO" if files are duplicates
- Currently disabled due to API quota

### **Layer 6: Find Outdated Files**
- Check last modified date
- If older than 6 months → mark as outdated

---

## **Setup Guide**

### **First Time Setup**

1. **Python is already installed** ✓ (in `.venv`)

2. **Packages are already installed** ✓
   - `google-genai` (for Gemini AI)
   - `python-dotenv` (for .env file)

3. **API Key Setup (Optional - for Gemini)**
   - Go to: https://aistudio.google.com/app/apikey
   - Create new API key
   - Open `.env` file
   - Replace with your key:
     ```
     GEMINI_API_KEY=your_key_here
     ```
   - Wait 24 hours for free quota to reset

---

## **Running the Program**

### **Option 1: From PowerShell**
```powershell
cd "d:\Data analysis tool"
& "D:/Data analysis tool/.venv/Scripts/python.exe" main.py
```

### **Option 2: From VS Code**
1. Open `main.py`
2. Press `Ctrl + F5` to run

---

## **What Each File Does**

| File | Purpose |
|------|---------|
| `main.py` | The main program - detects duplicates |
| `.env` | Stores your Gemini API key  |
| `data/` | Folder where you put files to analyze |
| `README.md` | This documentation |

---

## **Example Output Explained**

```
[EXACT] Exact Duplicate: photo.jpg <--> photo_backup.jpg
```
- These two files have **identical content**
- Definitely duplicates!

```
[NEAR] Near Duplicate Candidate: report_final.docx <--> report_final_v2.docx
  Name similarity: 98%
  Size difference: 5%
  Status: Strong candidate
```
- Names are **98% similar**
- Sizes are **only 5% different**
- Probably the same file!

```
[OLD] Outdated File: old_data.xlsx (last modified: 245.3 days ago)
```
- File hasn't been changed in **245 days** (over 6 months)
- suggested to deleted or archived

---

## **Troubleshooting**

### **Error: ModuleNotFoundError**
Solution: Run the install command:
```powershell
& "D:/Data analysis tool/.venv/Scripts/python.exe" -m pip install google-genai python-dotenv
```

### **Error: GEMINI_API_KEY not found**
Solution: 
1. Create `.env` file in project folder
2. Add: `GEMINI_API_KEY=your_key_here`
3. Save!

### **Error: No files in data folder**
Solution:
1. Create `data` folder if it doesn't exist
2. Add some files to it
3. Run again!

### **AI is giving warnings**
This is normal! It means:
- API quota reached (wait 24 hours)
- Or API key invalid (check `.env`)
- Program still works without AI!

---

## **Next Steps**

1. **Test the program** with some files
2. **Read the output** carefully
3. **Delete or organize** duplicate files
4. **Archive old files** from the [OLD] list

---

## **Features Summary**

✅ Exact duplicate detection (hash-based)  
✅ Near duplicate detection (name-based)  
✅ File size filtering (20% threshold)  
✅ Outdated file detection (6 months)  
✅ Gemini AI verification (optional)  
✅ Beginner-friendly code  
✅ Clean terminal output  
✅ No database required  

---

## **Hackathon Notes**

This is a **Proof of Concept (PoC)** for a hackathon project. It demonstrates:
- File system analysis
- Duplicate detection algorithms
- Metadata comparison
- AI integration (with Gemini)

**Great for:** 
- Learning file handling in Python
- Understanding duplicate detection
- Building AI-powered analysis tools

---

## **Questions?**

If something doesn't work:
1. Check the error message
2. Read the troubleshooting section
3. Make sure `.env` has your API key
4. Make sure `data/` folder has some files

---

**Happy analyzing!** 🚀

Created By : ARYAN VERMA and AADYAA SONI
Project: AI-Assisted Junk Detection Tool

