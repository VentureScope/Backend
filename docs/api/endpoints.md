# API Documentation

## Overview
VentureScope Backend provides a RESTful API for user authentication and career guidance features.

## Base URL
- **Development**: `http://localhost:8000`
- **Production**: TBD

## Authentication
The API uses JWT (JSON Web Token) bearer authentication for protected endpoints.

### Token Usage
```
Authorization: Bearer <your-jwt-token>
```

## Endpoints

### Health Check
- **GET** `/api/health`
- **Description**: Check API health status
- **Authentication**: None required
- **Response**: `{"status": "ok"}`

### Authentication

#### Register User
- **POST** `/api/auth/register`
- **Description**: Create new user account
- **Authentication**: None required
- **Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "securepassword",
    "full_name": "John Doe",
    "career_interest": "Software Engineering",
    "role": "professional"
  }
  ```
- **Response**:
  ```json
  {
    "id": "uuid",
    "email": "user@example.com", 
    "full_name": "John Doe",
    "github_username": null,
    "career_interest": "Software Engineering",
    "role": "professional"
  }
  ```

#### Login
- **POST** `/api/auth/login`
- **Description**: Authenticate user and get access token
- **Authentication**: None required
- **Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "securepassword"
  }
  ```
- **Response**:
  ```json
  {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "bearer"
  }
  ```

### User Management

#### Get Current User
- **GET** `/api/users/me`
- **Description**: Get current authenticated user information
- **Authentication**: Required (Bearer token)
- **Response**:
  ```json
  {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "John Doe",
    "github_username": null,
    "career_interest": "Software Engineering", 
    "role": "professional"
  }
  ```

## Error Responses

### Standard Error Format
```json
{
  "detail": "Error message description"
}
```

### HTTP Status Codes
- **200**: Success
- **400**: Bad Request - Invalid input data
- **401**: Unauthorized - Missing or invalid token
- **404**: Not Found - Resource doesn't exist
- **422**: Validation Error - Request body validation failed
- **500**: Internal Server Error

### Validation Errors
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

## Interactive Documentation
- **Swagger UI**: `/docs`
- **ReDoc**: `/redoc`

## Rate Limiting
Currently no rate limiting implemented. Consider implementing for production.

## Versioning
API is currently unversioned. Future versions should follow semantic versioning.

## Last Updated
April 2, 2026 - Initial API documentation