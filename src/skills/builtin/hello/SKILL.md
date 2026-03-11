---
name: hello
description: "A simple hello world skill demonstrating skill structure"
homepage: https://example.com
metadata: { "openclaw": { "emoji": "👋", "requires": {} } }
---

# Hello Skill

A simple demonstration skill that responds to greetings.

## When to Use

✅ **USE this skill when:**
- User says "hello" or "hi"
- User asks for a greeting
- Testing skill installation

## When NOT to Use

❌ **DON'T use this skill when:**
- User asks for complex tasks
- User needs data processing

## Commands

### Basic Greeting

```python
def greet(name: str = "World") -> str:
    return f"Hello, {name}! Welcome to scidatabot."
```

### Formal Greeting

```python
def greet_formal(name: str, title: str = "Mr./Ms.") -> str:
    return f"Hello, {title} {name}! How can I assist you today?"
```

## Examples

**Input:** "hello"
**Output:** "Hello! How can I help you today?"

**Input:** "hello Alice"
**Output:** "Hello, Alice! Welcome to scidatabot."
