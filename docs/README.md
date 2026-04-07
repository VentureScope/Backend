# Backend Documentation

This folder contains detailed documentation for the VentureScope Backend API.

## 📁 Documentation Structure

### When to Add Documentation

- **Feature Development**: Document new features, endpoints, or major functionality changes
- **Testing Updates**: Document testing strategies, coverage reports, or testing infrastructure changes  
- **Deployment Changes**: Document new deployment processes, environment setup, or infrastructure changes
- **Architecture Decisions**: Document significant architectural or design decisions
- **Troubleshooting**: Document common issues and their solutions

### What to Document

- **API Documentation**: Detailed endpoint specifications beyond auto-generated docs
- **Testing Reports**: Test coverage, performance benchmarks, testing strategies
- **Setup Guides**: Environment-specific setup instructions
- **Architecture**: System design, database schemas, service interactions
- **Deployment**: Production deployment guides, CI/CD documentation
- **Troubleshooting**: Common issues, debugging guides, FAQ

### How to Write Documentation

#### File Naming Convention
```
docs/
├── README.md                    # This file - documentation overview
├── api/                        # API-specific documentation
│   ├── endpoints.md            # Detailed endpoint documentation
│   └── authentication.md      # Auth implementation details
├── testing/                   # Testing documentation
│   ├── strategy.md            # Testing approach and guidelines
│   └── reports/               # Test reports and coverage
├── deployment/                # Deployment and operations
│   ├── docker.md              # Docker setup and configuration
│   └── production.md          # Production deployment guide
├── architecture/              # System design documentation
│   ├── database.md            # Database schema and design
│   └── services.md            # Service architecture overview
└── troubleshooting/           # Common issues and solutions
    └── common-issues.md
```

#### Writing Guidelines

1. **Use Clear Headings**: Structure with H1, H2, H3 for easy navigation
2. **Include Code Examples**: Provide practical examples and snippets
3. **Add Context**: Explain the "why" behind decisions, not just the "what"
4. **Keep Updated**: Review and update docs when code changes
5. **Link Related Docs**: Reference related documentation files

#### Template Format
```markdown
# Document Title

## Overview
Brief description of what this document covers.

## Prerequisites
What knowledge or setup is required to use this document.

## Detailed Content
The main content with examples, code snippets, and explanations.

## Related Documentation
Links to other relevant docs.

## Last Updated
[Date] - [Brief description of changes]
```

### Maintenance

- **Review Schedule**: Check documentation quarterly or after major releases
- **Update Process**: Update docs when making related code changes
- **Archive Policy**: Move outdated docs to `docs/archive/` with date stamps

### Contributing

When adding documentation:
1. Follow the naming convention above
2. Use the template format for consistency
3. Add an entry to this README if creating new categories
4. Update related documentation links

---

**Current Documentation:**

### API Endpoints
- [Real-Time WebSocket Chat](api/chat.md) - How to use the WebSockets, session management, and RAG architectures

### Testing
- [Testing Strategy](testing/strategy.md) - Testing approach, guidelines, and infrastructure
- [Test Commands](testing/commands.md) - How to run tests in Docker environment
- [Testing Report](testing/TESTING_COMPLETE.md) - Comprehensive test suite implementation

### Database
- [Migrations Guide](database/migrations.md) - Alembic database migrations workflow and commands

### Troubleshooting
- [Common Issues](troubleshooting/common-issues.md) - Solutions to common development and testing issues