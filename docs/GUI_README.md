# 🎧 Audiobook Processor GUI

A simple, cross-platform graphical interface for the Audiobook Processor that works on both Windows and Mac.

## 🚀 Quick Start

### Windows:
- Double-click `launch_gui.bat`
- Or run: `python audiobook_gui.py`

### Mac/Linux:
- Double-click `launch_gui.sh` (may need to make executable first)
- Or run: `python3 audiobook_gui.py`

## ✨ Features

- **🎯 Simple Interface**: Easy-to-use point-and-click interface
- **📁 Folder Browser**: Visual folder selection
- **⚙️ Configurable Options**: 
  - Bitrate selection (32k, 64k, 128k, 192k)
  - ZIP compression of original files
- **📊 Real-time Output**: Live processing updates
- **⏹️ Process Control**: Start/stop processing anytime
- **🔄 Progress Tracking**: Visual progress indicators
- **✅ Cross-platform**: Works on Windows, Mac, and Linux

## 🎛️ GUI Components

### Main Interface:
- **Folder Selection**: Browse and select your audiobook folder
- **Options Panel**:
  - **Compress original files**: Creates ZIP archives of source MP3s
  - **Bitrate**: Choose quality vs file size (32k = fastest, smallest)
- **Control Buttons**:
  - **🚀 Process Audiobooks**: Start batch processing
  - **⏹️ Stop Processing**: Cancel current operation
  - **🧹 Clear Output**: Clear the output window

### Output Window:
- **Real-time Processing Log**: See live progress updates
- **Status Bar**: Current operation status
- **Progress Bar**: Visual processing indicator

## 📋 How to Use

1. **Select Folder**: Click "Browse" and choose your audiobook folder
2. **Configure Options**: 
   - Choose bitrate (32k recommended for fastest processing)
   - Enable compression if you want to archive original files
3. **Start Processing**: Click "🚀 Process Audiobooks"
4. **Monitor Progress**: Watch the output window for real-time updates
5. **Results**: Processed M4A files will be created in each book's folder

## 🎯 What It Does

- **Combines** multiple MP3 files per book into single files
- **Converts** to optimized M4A format for better compatibility
- **Preserves** cover art and metadata
- **Compresses** original files (optional)
- **Organizes** output files in source folders

## 🔧 System Requirements

- **Python 3.6+** (includes tkinter)
- **FFmpeg** (for audio processing)
- **Windows, Mac, or Linux**

## 💡 Tips

- **32k bitrate** is perfect for audiobooks (fastest processing, good quality)
- **Enable compression** to save space while keeping originals safe
- **Large collections** may take time - use the stop button if needed
- **Check output window** for detailed progress and any issues

## 🐛 Troubleshooting

- **"Python not found"**: Install Python from python.org
- **"audiobook_processor.py not found"**: Keep GUI and processor files together
- **No MP3 files found**: Make sure your folder contains MP3 audiobooks
- **Processing stops**: Check output window for error details

## 📁 File Structure
```
audiobooks/
├── audiobook_gui.py          # Main GUI application
├── audiobook_processor.py    # Core processing engine
├── launch_gui.bat           # Windows launcher
└── launch_gui.sh            # Mac/Linux launcher
```

## 🎉 Example Workflow

1. You have: `Harry Potter/` with 20 MP3 files
2. Select the `Harry Potter/` folder in GUI
3. Click "🚀 Process Audiobooks"
4. Result: `Harry Potter.m4a` + `Harry Potter_original_files.zip`

Perfect for organizing large audiobook collections! 📚✨