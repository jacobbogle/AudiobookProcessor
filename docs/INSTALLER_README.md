# 📦 Audiobook Processor - Installation Package Creation

## 🎯 Overview

This directory contains everything needed to create professional installation packages for the Audiobook Processor application on both Windows and Mac platforms.

## 🏗️ Quick Setup

### For Windows Users
1. **Run the installer builder**:
   ```cmd
   build_windows_installer.bat
   ```
2. **Output**: `AudiobookProcessor_Setup_v2.0.exe`

### For Mac Users  
1. **Make script executable and run**:
   ```bash
   chmod +x build_mac_installer.sh
   ./build_mac_installer.sh
   ```
2. **Output**: `AudiobookProcessor.app` and installer package

## 📁 Package Contents

### Core Application Files
- `audiobook_processor.py` - Main processing engine
- `audiobook_gui.py` - Standard GUI interface
- `parallel_audiobook_processor.py` - Multi-core processing
- `parallel_audiobook_gui.py` - Parallel processing GUI
- `power_manager.py` - Windows power management system

### Installation Scripts
- `installer_windows.nsi` - NSIS installer configuration
- `build_windows_installer.bat` - Windows installer builder
- `build_mac_installer.sh` - Mac application bundle and installer builder

### Icons and Assets
- `icons/audiobook_processor.svg` - Scalable vector icon
- `icons/` directory for platform-specific icon formats

### Documentation
- `DEPLOYMENT_GUIDE.md` - Comprehensive deployment instructions
- `README.md` - User documentation
- `GUI_README.md` - GUI-specific help

## 🛠️ Prerequisites

### Windows Development
- **NSIS** - Download from https://nsis.sourceforge.io/
- **ImageMagick** (optional) - For icon conversion
- **Code signing certificate** (optional) - For trusted installations

### Mac Development
- **Xcode Command Line Tools** - `xcode-select --install`
- **Python 3.7+** - Should be pre-installed or via Homebrew
- **Developer ID certificate** (optional) - For code signing

## 🎨 Icon Requirements

The installer expects these icon files:

### Windows
- `icons/audiobook_processor.ico` - Main application icon
- `icons/header.bmp` - Installer header image (150x57 pixels)
- `icons/wizard.bmp` - Installer wizard image (164x314 pixels)

### Mac
- `icons/audiobook_processor.icns` - Mac application icon bundle

**Convert the provided SVG using the instructions in `DEPLOYMENT_GUIDE.md`**

## 🚀 Building Installers

### Windows NSIS Installer

**Features:**
- Professional Windows installer
- System requirements checking
- Desktop and Start Menu shortcuts
- File associations for audiobook formats
- Uninstaller creation
- Registry integration

**Build Process:**
1. Ensure NSIS is installed and in PATH
2. Convert SVG icon to ICO format
3. Run `build_windows_installer.bat`
4. Test the generated installer

### Mac Application Bundle

**Features:**
- Native macOS app bundle
- Proper Info.plist configuration
- File type associations
- Python environment detection
- Launcher command files

**Build Process:**
1. Ensure Xcode Command Line Tools installed
2. Convert SVG icon to ICNS format
3. Run `build_mac_installer.sh`
4. Test both the app bundle and PKG installer

## 📋 Installation Features

### Windows Installer Components
- **Core Application**: Required files (cannot be deselected)
- **Desktop Shortcuts**: Quick access icons on desktop
- **Start Menu Shortcuts**: Programs menu integration
- **File Associations**: Open audiobook files with the app

### Mac Installation Options
- **App Bundle**: Drag-and-drop to Applications
- **PKG Installer**: Guided installation process
- **Command Line Tools**: Terminal-accessible launchers

## 🔐 Code Signing (Recommended)

### Why Sign Your Application?
- **Trust**: Users can verify the publisher
- **Security**: Prevents tampering warnings
- **Store Distribution**: Required for app stores

### Windows Code Signing
```cmd
signtool sign /f your_certificate.pfx /p password AudiobookProcessor_Setup_v2.0.exe
```

### Mac Code Signing
```bash
codesign --sign "Developer ID Application: Your Name" AudiobookProcessor.app
```

## 📊 Distribution Strategies

### 1. Direct Distribution
- Host installer files on your website
- Provide download links for both platforms
- Include system requirements and installation instructions

### 2. GitHub Releases
- Upload installers as release assets
- Use semantic versioning (v2.0, v2.1, etc.)
- Include release notes and changelogs

### 3. App Store Distribution
- Windows: Microsoft Store (.msix package)
- Mac: Mac App Store (requires additional setup)

## 🐛 Troubleshooting

### Common Build Issues

**Windows:**
- "NSIS not found": Install NSIS and add to PATH
- "Icon file missing": Convert SVG to ICO format
- "License file missing": Will be auto-created by build script

**Mac:**
- "Command not found": Install Xcode Command Line Tools
- "Permission denied": Run `chmod +x build_mac_installer.sh`
- "Icon conversion failed": Manually convert SVG to ICNS

### Installation Issues

**Windows:**
- "Python not detected": Installer will prompt user to install
- "FFmpeg warning": User can continue without FFmpeg
- "Administrator required": Normal for system-wide installation

**Mac:**
- "App can't be opened": Enable "Allow apps downloaded from anywhere"
- "Python not found": User needs to install Python 3.7+
- "Permission issues": Try installing with `sudo` for PKG

## 📈 Version Management

### Updating Version Numbers
1. Edit version in `installer_windows.nsi`
2. Edit version in `build_mac_installer.sh`
3. Update documentation and changelogs
4. Rebuild installers with new version

### Release Checklist
- [ ] Update version numbers
- [ ] Test on clean systems
- [ ] Update documentation
- [ ] Create release notes
- [ ] Build and sign installers
- [ ] Upload to distribution channels

---

**Ready to create professional installers for your audiobook processing application!** 🎧✨