#!/usr/bin/env python3
"""Test complete config workflow: save/load with multiple agents."""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui.config_store import ConfigStore


def test_config_workflow():
    """Test full configuration workflow."""
    print("=" * 60)
    print("Testing Config Workflow (Save/Load/Encrypt)")
    print("=" * 60)
    
    store = ConfigStore(workspace_root=PROJECT_ROOT)
    
    # Load or create config
    config = store.load_config()
    print("\n📋 Loaded initial config")
    print(f"   Active key ID: {config['key_store']['active_key_id']}")
    print(f"   Global loop budget: {config['loop']['global_loop_budget']}")
    
    # Configure multiple agents with API keys
    agents_config = {
        "openai_agent": {
            "model": "gpt-4",
            "top_k": 5,
            "top_p": 0.9,
            "temperature": 0.7,
            "api_key_enc": None,  # Will be encrypted
        },
        "anthropic_agent": {
            "model": "claude-3-opus",
            "top_k": 3,
            "top_p": 0.95,
            "temperature": 0.5,
            "api_key_enc": None,  # Will be encrypted
        },
        "local_agent": {
            "model": "llama2-7b",
            "top_k": 10,
            "top_p": 0.8,
            "temperature": 0.6,
            "api_key_enc": None,
        },
    }
    
    # Encrypt API keys
    api_keys = {
        "openai_agent": "sk-openai-abcdef1234567890",
        "anthropic_agent": "sk-ant-abcdef1234567890",
        "local_agent": "sk-local-abcdef1234567890",
    }
    
    print("\n🔐 Encrypting API keys for each agent...")
    for agent_name, api_key in api_keys.items():
        encrypted = store.encrypt_api_key(api_key, config)
        agents_config[agent_name]["api_key_enc"] = encrypted
        print(f"   ✓ {agent_name}: {encrypted['key_id']}")
    
    # Save config
    config["agents"] = agents_config
    store.save_config(config)
    print(f"\n💾 Config saved to {store.config_path}")
    
    # Reload and verify
    print("\n🔄 Reloading config from disk...")
    reloaded = store.load_config()
    
    # Test decryption
    print("\n🔓 Decrypting API keys...")
    for agent_name in api_keys:
        encrypted_data = reloaded["agents"][agent_name]["api_key_enc"]
        decrypted = store.decrypt_api_key(encrypted_data, reloaded)
        
        if decrypted == api_keys[agent_name]:
            print(f"   ✅ {agent_name}: decrypted correctly")
        else:
            print(f"   ❌ {agent_name}: decryption mismatch!")
            return False
    
    # Show config structure
    print("\n📦 Final config structure (keys masked):")
    config_view = {
        "agents": {
            agent: {
                "model": cfg["model"],
                "top_k": cfg["top_k"],
                "top_p": cfg["top_p"],
                "temperature": cfg["temperature"],
                "api_key_enc": {
                    "key_id": cfg["api_key_enc"]["key_id"] if cfg["api_key_enc"] else None,
                    "encrypted_aes_key": f"{cfg['api_key_enc']['encrypted_aes_key'][:20]}..." if cfg["api_key_enc"] else None,
                }
            }
            for agent, cfg in reloaded["agents"].items()
        },
        "loop": reloaded["loop"],
    }
    print(json.dumps(config_view, ensure_ascii=False, indent=2))
    
    print("\n✅ Config workflow test PASSED!")
    return True


if __name__ == "__main__":
    success = test_config_workflow()
    sys.exit(0 if success else 1)
