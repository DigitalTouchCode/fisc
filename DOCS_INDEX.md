# FiscGuy Documentation Index

Welcome to FiscGuy documentation! This guide helps you navigate the different documentation files based on your role and needs.

## 📚 Documentation Files Overview

### For New Users & Integration

**Start here if you're:**
- Installing FiscGuy for the first time
- Integrating FiscGuy into your Django project
- Building a client application
- Looking for API examples

**Read:**
1. **[USER_GUIDE.md](USER_GUIDE.md)** (15K) - Complete user guide with:
   - Installation steps
   - Quick start (5-minute setup)
   - Full API endpoint reference
   - 4 practical usage examples
   - Concepts & terminology
   - 30+ FAQs and troubleshooting

2. **[README.md](README.md)** (9K) - Project overview with:
   - Feature highlights
   - Installation options
   - Environment switching guide
   - Basic setup instructions

---

### For Developers & Maintainers

**Read if you're:**
- Contributing to FiscGuy
- Understanding internal architecture
- Adding new features
- Debugging issues
- Designing integrations

**Read:**
1. **[ARCHITECTURE.md](ARCHITECTURE.md)** (24K) - Technical deep dive covering:
   - Layered architecture (REST → Services → Models → ZIMRA)
   - Complete data model documentation
   - Service layer details
   - Cryptographic operations
   - ZIMRA FDMS integration
   - Receipt processing pipeline
   - Fiscal day management
   - Database design & indexes
   - Development guidelines

2. **[CONTRIBUTING.md](CONTRIBUTING.md)** (6K) - Contribution guidelines with:
   - Code style requirements (Black, isort, flake8)
   - Test requirements
   - PR process
   - Issue reporting

---

### For Integration & DevOps

**Read if you're:**
- Deploying FiscGuy to production
- Setting up ZIMRA environment
- Managing certificates
- Configuring Django settings

**Read:**
1. **[INSTALL.md](INSTALL.md)** (6K) - Detailed installation guide
2. **[USER_GUIDE.md](USER_GUIDE.md)** - Quick Start section (Step 1-5)
3. **[ARCHITECTURE.md](ARCHITECTURE.md)** - Deployment considerations section

---

### API Reference

**For API endpoint details, request/response examples, and error codes:**

**Read:**
1. **[USER_GUIDE.md](USER_GUIDE.md#api-endpoints)** - Quick API reference with curl examples
2. **[endpoints.md](endpoints.md)** - Detailed API specification
3. **[ARCHITECTURE.md](ARCHITECTURE.md#zimra-integration)** - ZIMRA payload specifications

---

## Quick Navigation

| Need | Document | Section |
|------|----------|---------|
| Install FiscGuy | [USER_GUIDE.md](USER_GUIDE.md#installation) | Installation |
| Setup project | [USER_GUIDE.md](USER_GUIDE.md#quick-start) | Quick Start |
| API examples | [USER_GUIDE.md](USER_GUIDE.md#usage-examples) | Usage Examples |
| Troubleshoot | [USER_GUIDE.md](USER_GUIDE.md#troubleshooting) | Troubleshooting |
| Answer a question | [USER_GUIDE.md](USER_GUIDE.md#faq) | FAQ |
| Understand architecture | [ARCHITECTURE.md](ARCHITECTURE.md#architecture) | Architecture |
| Data models | [ARCHITECTURE.md](ARCHITECTURE.md#data-models) | Data Models |
| Services | [ARCHITECTURE.md](ARCHITECTURE.md#service-layer) | Service Layer |
| Cryptography | [ARCHITECTURE.md](ARCHITECTURE.md#cryptography--security) | Cryptography |
| ZIMRA API | [ARCHITECTURE.md](ARCHITECTURE.md#zimra-integration) | ZIMRA Integration |
| Receipt flow | [ARCHITECTURE.md](ARCHITECTURE.md#receipt-processing-pipeline) | Receipt Pipeline |
| Dev guidelines | [ARCHITECTURE.md](ARCHITECTURE.md#development-guidelines) | Dev Guidelines |
| Contribute | [CONTRIBUTING.md](CONTRIBUTING.md) | All |

---

## Documentation Philosophy

**FiscGuy documentation is organized by audience:**

1. **[USER_GUIDE.md](USER_GUIDE.md)** - Practical, example-driven, task-focused
   - How do I...?
   - Why does this happen?
   - What does this mean?

2. **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical, comprehensive, reference-style
   - How does this work?
   - What are the relationships?
   - What are the constraints?

3. **[CONTRIBUTING.md](CONTRIBUTING.md)** - Process-focused, standards-based
   - How do I contribute?
   - What are the standards?

4. **[endpoints.md](endpoints.md)** - Specification-style
   - What are all the endpoints?
   - What are request/response formats?

---

## Version Information

- **Current Version:** 0.1.6 (unreleased)
- **Python:** 3.11, 3.12, 3.13
- **Django:** 4.2+
- **DRF:** 3.14+
- **Last Updated:** April 1, 2026

---

## Getting Help

| Question Type | Where to Look |
|---------------|---------------|
| "How do I...?" | [USER_GUIDE.md](USER_GUIDE.md) |
| "Why isn't it working?" | [USER_GUIDE.md#troubleshooting](USER_GUIDE.md#troubleshooting) |
| "I have a question" | [USER_GUIDE.md#faq](USER_GUIDE.md#faq) |
| "How does it work?" | [ARCHITECTURE.md](ARCHITECTURE.md) |
| "I want to contribute" | [CONTRIBUTING.md](CONTRIBUTING.md) |
| "I need API details" | [endpoints.md](endpoints.md) |
| "Issues/bugs" | https://github.com/digitaltouchcode/fisc/issues |
| "Email support" | cassymyo@gmail.com |

---

## Documentation Standards

All FiscGuy documentation:
- ✅ Uses Markdown with proper formatting
- ✅ Includes table of contents for long documents
- ✅ Provides practical examples
- ✅ Follows clear structure (concept → details → examples)
- ✅ Includes appropriate diagrams/flowcharts
- ✅ Is kept in sync with code changes
- ✅ Is reviewed in pull requests

---

## Recent Documentation Updates

**Version 0.1.6:**
- Added ARCHITECTURE.md (comprehensive internal documentation)
- Added USER_GUIDE.md (comprehensive user documentation)
- Updated CHANGELOG.md with device field fix
- Added device field to ReceiptCreateSerializer

See [CHANGELOG.md](CHANGELOG.md) for full version history.

---

**Happy coding! 🚀**

For quick help, start with [USER_GUIDE.md](USER_GUIDE.md).  
For technical depth, see [ARCHITECTURE.md](ARCHITECTURE.md).
