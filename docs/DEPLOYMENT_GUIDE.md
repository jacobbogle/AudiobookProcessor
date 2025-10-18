# Icon Conversion and Deployment Guide

## 🎨 Converting Icons for Different Platforms

### From SVG to Platform-Specific Formats

The provided `audiobook_processor.svg` needs to be converted to platform-specific formats:

#### Windows (.ICO)
```bash
# Using ImageMagick
magick audiobook_processor.svg -resize 256x256 audiobook_processor.ico

# Using online converter
# 1. Upload audiobook_processor.svg to https://convertio.co/svg-ico/
# 2. Download and save as icons/audiobook_processor.ico
```

#### Mac (.ICNS)
```bash
# Using sips (macOS built-in)
mkdir audiobook_processor.iconset
sips -z 16 16 audiobook_processor.svg --out audiobook_processor.iconset/icon_16x16.png
sips -z 32 32 audiobook_processor.svg --out audiobook_processor.iconset/icon_16x16@2x.png
sips -z 32 32 audiobook_processor.svg --out audiobook_processor.iconset/icon_32x32.png
sips -z 64 64 audiobook_processor.svg --out audiobook_processor.iconset/icon_32x32@2x.png
sips -z 128 128 audiobook_processor.svg --out audiobook_processor.iconset/icon_128x128.png
sips -z 256 256 audiobook_processor.svg --out audiobook_processor.iconset/icon_128x128@2x.png
sips -z 256 256 audiobook_processor.svg --out audiobook_processor.iconset/icon_256x256.png
sips -z 512 512 audiobook_processor.svg --out audiobook_processor.iconset/icon_256x256@2x.png
sips -z 512 512 audiobook_processor.svg --out audiobook_processor.iconset/icon_512x512.png
iconutil -c icns audiobook_processor.iconset

# Using online converter
# 1. Upload to https://cloudconvert.com/svg-to-icns
# 2. Download and save as icons/audiobook_processor.icns
```

## 📦 Building Installers

### Windows Installer (NSIS)

1. **Install NSIS**: Download from https://nsis.sourceforge.io/
2. **Convert icons**: Place `audiobook_processor.ico` in `icons/` folder
3. **Build installer**:
   ```cmd
   build_windows_installer.bat
   ```

**Output**: `AudiobookProcessor_Setup_v2.0.exe`

### Mac Installer (PKG)

1. **Prepare environment**: Ensure Xcode Command Line Tools installed
2. **Convert icons**: Place `audiobook_processor.icns` in `icons/` folder  
3. **Build installer**:
   ```bash
   chmod +x build_mac_installer.sh
   ./build_mac_installer.sh
   ```

**Output**: `AudiobookProcessor.app` and `AudiobookProcessor_Installer_v2.0.pkg`

## 🚀 Deployment Checklist

### Pre-Distribution Testing

#### Windows
- [ ] Test installer on clean Windows system
- [ ] Verify Python detection works
- [ ] Verify FFmpeg detection works
- [ ] Test desktop shortcuts
- [ ] Test Start Menu integration
- [ ] Test file associations
- [ ] Test uninstaller

#### Mac
- [ ] Test app bundle on clean macOS system
- [ ] Verify Python detection works
- [ ] Test drag-to-Applications installation
- [ ] Test PKG installer
- [ ] Verify file associations work
- [ ] Test on both Intel and Apple Silicon Macs

### Distribution Options

#### Windows
1. **Simple Distribution**: ZIP file with portable version
2. **Professional Distribution**: Signed NSIS installer (.exe)
3. **Store Distribution**: Microsoft Store package (.msix)

#### Mac
1. **Simple Distribution**: ZIP with app bundle
2. **Professional Distribution**: Signed PKG installer
3. **Store Distribution**: Mac App Store package

### Code Signing (Recommended)

#### Windows
```cmd
signtool sign /f certificate.pfx /p password AudiobookProcessor_Setup_v2.0.exe
```

#### Mac
```bash
codesign --sign "Developer ID Application: Your Name" AudiobookProcessor.app
productbuild --sign "Developer ID Installer: Your Name" --component AudiobookProcessor.app /Applications AudiobookProcessor_Signed.pkg
```

## 📋 Installation Requirements

### End User Requirements

#### Windows
- Windows 7 SP1 or later (Windows 10+ recommended)
- Python 3.7 or later
- FFmpeg (automatic installation option in installer)
- 100MB free disk space

#### Mac  
- macOS 10.12 Sierra or later (macOS 11+ recommended)
- Python 3.7 or later
- FFmpeg (can install via Homebrew)
- 100MB free disk space

### Optional Enhancements
- Digital signature for trusted installation
- Auto-updater integration
- Crash reporting system
- Usage analytics (with user consent)

## 🔧 Build Tools Installation

### Windows Development Environment
```cmd
# Install NSIS
winget install NSIS.NSIS

# Install ImageMagick (for icon conversion)
winget install ImageMagick.ImageMagick
```

### Mac Development Environment
```bash
# Install Xcode Command Line Tools
xcode-select --install

# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install ImageMagick (for icon conversion)
brew install imagemagick
```

## 📝 Release Notes Template

Use this template for release documentation:

```markdown
# Audiobook Processor v2.0 Release Notes

## 🆕 New Features
- Single file processing with metadata application
- Parent folder batch processing
- Windows power management (prevents sleep during processing)
- Enhanced series organization and detection
- Parallel processing support
- Cross-platform GUI interface

## 🛠️ Installation
- **Windows**: Run AudiobookProcessor_Setup_v2.0.exe
- **Mac**: Drag AudiobookProcessor.app to Applications folder

## 📋 System Requirements
- **Windows**: Windows 7+ with Python 3.7+
- **Mac**: macOS 10.12+ with Python 3.7+
- **Both**: FFmpeg recommended for audio processing

## 🐛 Known Issues
- Power management only available on Windows
- GUI requires tkinter (usually included with Python)
```

---
*For support and updates, visit the project documentation.*