# AunooAI Specification Modules

This directory contains modular specifications for different aspects of the AunooAI platform. Each specification file focuses on a specific domain while maintaining consistency with the main specification.

## Specification Files

### [database.md](database.md) - Database Schema Specification
Complete database schema definition including:
- Table definitions with all fields and constraints
- Indexes and performance optimizations
- Foreign key relationships
- Data validation rules
- Migration system documentation
- Backup and recovery procedures

## Usage with AI Agents

### Referencing Specific Specs

When working with AI agents, reference specific specification files:

**For database operations:**
```
@specs/database.md implement user authentication table operations
```

**For API development:**
```
@main.md implement REST endpoints following @specs/database.md schema
```

### Cross-Reference Pattern

Each specification file should:
1. **Reference main.md** for overall context
2. **Be self-contained** for its domain
3. **Use consistent terminology** across all specs
4. **Include practical examples** for AI agents

## Adding New Specifications

When creating new specification files:

1. **Create focused domain file** (e.g., `api.md`, `security.md`)
2. **Update this README** to include the new file
3. **Update main.md** to reference the new spec
4. **Use consistent formatting** across all specs
5. **Include practical examples** and code patterns

## Specification Standards

### File Structure
```markdown
# Domain Name - Purpose

## Overview
Brief description of the domain

## Configuration
Environment variables and settings

## Core Components
Main entities and their relationships

## Implementation Details
Technical specifications and patterns

## Examples
Code examples and usage patterns
```

### Cross-References
- Use relative links between spec files
- Reference main.md for overall context
- Link to related specifications when relevant

### Terminology
- Use consistent terms across all specifications
- Define acronyms on first use
- Use precise technical language

## Benefits of Modular Specifications

1. **Focused Development**: AI agents can focus on specific domains
2. **Easier Maintenance**: Update specific areas without affecting others
3. **Better Organization**: Related information grouped together
4. **Reduced Complexity**: Smaller, more manageable specification files
5. **Team Collaboration**: Different team members can own different specs

## Integration with Main Specification

The main specification (`../main.md`) serves as:
- **Overview and context** for the entire system
- **Cross-domain relationships** between specifications
- **Entry point** for new developers
- **Reference guide** for AI agents

Individual specification files provide:
- **Detailed domain knowledge** for specific areas
- **Implementation patterns** and examples
- **Technical specifications** for AI code generation
- **Validation criteria** for implementations
