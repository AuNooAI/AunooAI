---
mode: agent
---

# AunooAI Compilation Instructions

Update the AunooAI application to follow [the specification](./main.md). This prompt guides the AI coding agent to implement, maintain, and enhance the AunooAI research and analysis platform.

## Compilation Goals

### Primary Objectives
- Implement the complete AunooAI platform as specified in main.md
- Maintain existing functionality while improving architecture
- Ensure all components work together seamlessly
- Follow FastAPI and Python best practices
- Implement proper error handling and logging
- Maintain database integrity and performance

### Code Quality Standards
- Use type hints for all function signatures
- Implement proper async/await patterns
- Follow SOLID principles and clean architecture
- Use dependency injection for better testability
- Implement comprehensive error handling
- Maintain consistent logging throughout the application

## Implementation Guidelines

### FastAPI Application Structure
- Use FastAPI with async support for all I/O operations
- Implement proper middleware for authentication, logging, and error handling
- Use Pydantic models for request/response validation
- Implement proper HTTP status codes and error responses
- Use dependency injection for database connections and services

### Database Layer
- Maintain SQLAlchemy models as defined in database_models.py
- Implement proper connection pooling and transaction management
- Use database migrations for schema changes
- Implement proper indexing for performance
- Handle concurrent access with WAL mode

### AI Integration
- Implement multi-provider AI model support (OpenAI, Anthropic, HuggingFace, Gemini)
- Use LiteLLM for unified model interface
- Implement proper prompt management and templating
- Handle API rate limits and errors gracefully
- Cache AI responses when appropriate

### Data Collection Pipeline
- Implement modular collectors for different data sources
- Use async processing for data collection
- Implement proper error handling and retry logic
- Handle rate limiting and API quotas
- Implement data validation and deduplication

### Web Interface
- Use Jinja2 templates with Bootstrap 5 for responsive design
- Implement proper form validation and CSRF protection
- Use JavaScript for interactive features
- Implement real-time updates via WebSocket
- Ensure accessibility and mobile responsiveness

### Security Implementation
- Implement proper authentication and authorization
- Use session-based authentication with secure cookies
- Implement input validation and sanitization
- Use HTTPS in production environments
- Implement proper error handling without information disclosure

## Development Workflow

### Build Process
1. **Environment Setup**: Ensure all dependencies are properly configured
2. **Database Migration**: Run any pending database migrations
3. **Code Compilation**: Build the FastAPI application
4. **Testing**: Run unit and integration tests
5. **Validation**: Verify all endpoints and functionality work correctly

### Testing Strategy
- Unit tests for core business logic
- Integration tests for API endpoints
- Database migration testing
- Performance testing for critical paths
- Security testing for authentication and authorization

### Code Organization
- Keep existing file structure and organization
- Maintain separation of concerns
- Use proper imports and module structure
- Implement consistent naming conventions
- Document complex business logic

## Specific Implementation Areas

### API Routes
- Implement all routes as specified in main.md
- Use proper HTTP methods and status codes
- Implement request/response validation with Pydantic
- Handle authentication and authorization
- Implement proper error handling

### Database Operations
- Use SQLAlchemy for all database operations
- Implement proper transaction management
- Use connection pooling for performance
- Handle database errors gracefully
- Implement proper indexing and query optimization

### AI Model Integration
- Implement the multi-provider AI system
- Handle API key management securely
- Implement proper error handling for AI services
- Use caching for expensive AI operations
- Implement proper logging for AI interactions

### Data Collection
- Implement all collector modules
- Handle different data source APIs
- Implement proper error handling and retries
- Use async processing for better performance
- Implement data validation and cleaning

### Web Interface
- Implement all web pages and forms
- Use responsive design with Bootstrap 5
- Implement proper form validation
- Use JavaScript for interactive features
- Ensure proper accessibility

## Error Handling and Logging

### Logging Strategy
- Use structured logging throughout the application
- Implement different log levels (DEBUG, INFO, WARNING, ERROR)
- Log all API requests and responses
- Log database operations and errors
- Log AI model interactions and errors

### Error Handling
- Implement graceful error handling for all operations
- Return appropriate HTTP status codes
- Provide user-friendly error messages
- Log detailed error information for debugging
- Implement retry logic for transient failures

## Performance Optimization

### Database Performance
- Use proper indexing for frequently queried fields
- Implement connection pooling
- Use WAL mode for concurrent access
- Optimize queries for performance
- Implement caching for expensive operations

### API Performance
- Use async/await for all I/O operations
- Implement proper caching strategies
- Use pagination for large result sets
- Implement rate limiting
- Monitor and optimize response times

## Security Considerations

### Authentication and Authorization
- Implement secure session management
- Use proper password hashing
- Implement role-based access control
- Validate all user inputs
- Implement CSRF protection

### Data Protection
- Encrypt sensitive data
- Implement proper API key management
- Use HTTPS for all communications
- Validate and sanitize all inputs
- Implement proper error handling without information disclosure

## Deployment Considerations

### Docker Support
- Maintain existing Docker configuration
- Ensure proper environment variable handling
- Implement health checks
- Optimize container size and startup time

### Cloud Deployment
- Support Google Cloud Run deployment
- Implement proper scaling configuration
- Use environment-specific configurations
- Implement proper monitoring and logging

## Maintenance and Updates

### Code Maintenance
- Keep dependencies up to date
- Implement proper versioning
- Maintain backward compatibility
- Implement proper migration strategies
- Document all changes

### Monitoring
- Implement application monitoring
- Monitor database performance
- Track API usage and errors
- Monitor AI model performance
- Implement alerting for critical issues

## Validation Checklist

Before considering the compilation complete, verify:

- [ ] All API endpoints are implemented and working
- [ ] Database operations are properly implemented
- [ ] AI model integration is working correctly
- [ ] Data collection pipeline is functional
- [ ] Web interface is responsive and accessible
- [ ] Authentication and authorization work properly
- [ ] Error handling is comprehensive
- [ ] Logging is properly implemented
- [ ] Performance is optimized
- [ ] Security measures are in place
- [ ] Tests are passing
- [ ] Documentation is up to date

## Focus Areas for Current Session

When implementing changes, focus on:

1. **Maintaining Existing Functionality**: Ensure all current features continue to work
2. **Improving Architecture**: Enhance code organization and maintainability
3. **Adding Missing Features**: Implement any missing functionality from the specification
4. **Performance Optimization**: Improve database and API performance
5. **Security Enhancement**: Strengthen authentication and data protection
6. **Error Handling**: Improve error handling and user experience
7. **Testing**: Ensure comprehensive test coverage
8. **Documentation**: Keep documentation current and comprehensive

## Build Commands

Use the following commands to build and test the application:

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
python run_migration.py

# Start the development server
python app/main.py

# Run tests
python -m pytest tests/

# Build Docker image
docker-compose build

# Run in Docker
docker-compose up -d
```

## Success Criteria

The compilation is successful when:

1. All specified functionality is implemented and working
2. The application starts without errors
3. All API endpoints respond correctly
4. Database operations work properly
5. AI integration is functional
6. Web interface is accessible and responsive
7. Authentication and security are properly implemented
8. Performance meets requirements
9. Tests are passing
10. Code quality meets standards

Focus on implementing the specification accurately while maintaining code quality and following best practices. Avoid making unnecessary changes to working code unless specifically required by the specification.
