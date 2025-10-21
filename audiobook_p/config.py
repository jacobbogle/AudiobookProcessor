# -*- coding: utf-8 -*-
"""
Configuration management for audiobook processing.
"""

import json
import os
# from typing import Dict, Any, Optional  # Removed for Python 2.7 compatibility


class Config:
    """Configuration manager for audiobook-p"""
    
    DEFAULT_CONFIG = {
        "processing": {
            "ffmpeg_quality": "128k",
            "chapter_naming": "Chapter {number}",
            "overwrite_existing": False,
            "preserve_original": True,
            "parallel_processing": True,
            "max_workers": 4
        },
        "metadata": {
            "default_genre": "Audiobook",
            "auto_set_audiobook_tags": True,
            "preserve_cover_art": True,
            "encoding_tool_tag": "audiobook-p"
        },
        "output": {
            "default_format": "m4b",
            "create_subdirectories": True,
            "filename_template": "{album}",
            "progress_reporting": True
        },
        "validation": {
            "strict_mode": False,
            "skip_corrupted_files": True,
            "minimum_file_size": 1024,
            "allowed_extensions": [".mp3", ".m4a", ".m4b"]
        }
    }
    
    CONFIG_FILENAME = ".audiobook-p.json"
    
    def __init__(self):
        self.config = self.DEFAULT_CONFIG.copy()
        self.config_path = None
        self._load_config()
    
    def _find_config_file(self):
        """Find the configuration file in standard locations"""
        search_paths = [
            os.path.join(os.getcwd(), self.CONFIG_FILENAME),
            os.path.join(os.path.expanduser("~"), self.CONFIG_FILENAME),
            os.path.join(os.path.expanduser("~"), ".config", "audiobook-p", "config.json")
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _load_config(self):
        """Load configuration from file"""
        config_path = self._find_config_file()
        if config_path:
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                
                # Merge with defaults
                self._deep_merge(self.config, user_config)
                self.config_path = config_path
                
            except (json.JSONDecodeError, IOError) as e:
                print("Warning: Could not load config from {}: {}".format(config_path, e))
    
    def _deep_merge(self, base_dict, update_dict):
        """Recursively merge update_dict into base_dict"""
        for key, value in update_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._deep_merge(base_dict[key], value)
            else:
                base_dict[key] = value
    
    def get(self, key_path, default=None):
        """
        Get a configuration value using dot notation.
        
        Args:
            key_path: Path to the config value (e.g., 'processing.ffmpeg_quality')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key_path, value):
        """
        Set a configuration value using dot notation.
        
        Args:
            key_path: Path to the config value (e.g., 'processing.ffmpeg_quality')
            value: Value to set
        """
        keys = key_path.split('.')
        config_section = self.config
        
        # Navigate to the parent of the final key
        for key in keys[:-1]:
            if key not in config_section:
                config_section[key] = {}
            config_section = config_section[key]
        
        # Set the final value
        config_section[keys[-1]] = value
    
    def save(self, path=None):
        """
        Save current configuration to file.
        
        Args:
            path: Optional custom path to save to
        """
        if path:
            save_path = path
        elif self.config_path:
            save_path = self.config_path
        else:
            # Default to user's home directory
            save_path = os.path.join(os.path.expanduser("~"), self.CONFIG_FILENAME)
        
        # Ensure directory exists
        # Create directory if it doesn't exist (Python 2.7 compatible)
        save_dir = os.path.dirname(save_path)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        try:
            with open(save_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            print("Configuration saved to: {}".format(save_path))
            self.config_path = save_path
            
        except IOError as e:
            print("Error saving configuration: {}".format(e))
    
    def reset_to_defaults(self):
        """Reset configuration to default values"""
        self.config = self.DEFAULT_CONFIG.copy()
    
    def show_config(self):
        """Display current configuration"""
        print("Current Configuration:")
        print(json.dumps(self.config, indent=2))
    
    def get_processing_settings(self):
        """Get processing-specific settings"""
        return self.config.get('processing', {})
    
    def get_metadata_settings(self):
        """Get metadata-specific settings"""
        return self.config.get('metadata', {})
    
    def get_output_settings(self):
        """Get output-specific settings"""
        return self.config.get('output', {})
    
    def get_validation_settings(self):
        """Get validation-specific settings"""
        return self.config.get('validation', {})


# Global config instance
_config_instance = None


def get_config():
    """Get the global configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


def create_default_config_file(path=None):
    """
    Create a default configuration file for user customization.
    
    Args:
        path: Optional custom path for the config file
    """
    config = Config()
    config.reset_to_defaults()
    
    if not path:
        path = os.path.join(os.path.expanduser("~"), Config.CONFIG_FILENAME)
    
    # Add comments to the JSON for user guidance
    config_with_comments = {
        "_comment": "AudiobookProcessor Configuration File",
        "_usage": "Modify values below to customize audiobook processing behavior"
    }
    config_with_comments.update(config.config)
    
    # Create directory if it doesn't exist (Python 2.7 compatible)
    config_dir = os.path.dirname(path)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    
    with open(path, 'w') as f:
        json.dump(config_with_comments, f, indent=2)
    
    print("Default configuration file created at: {}".format(path))
    print("Edit this file to customize audiobook processing settings.")


if __name__ == "__main__":
    # Test configuration system
    print("Testing configuration system...")
    
    config = get_config()
    
    print("FFmpeg quality: {}".format(config.get('processing.ffmpeg_quality')))
    print("Default genre: {}".format(config.get('metadata.default_genre')))
    print("Progress reporting: {}".format(config.get('output.progress_reporting')))
    
    # Test setting a value
    config.set('processing.ffmpeg_quality', '192k')
    print("Updated FFmpeg quality: {}".format(config.get('processing.ffmpeg_quality')))
    
    print("Configuration system ready")