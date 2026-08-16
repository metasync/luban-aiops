# Operator Portal

<cite>
**Referenced Files in This Document**
- [index.html](file://products/operator-portal/web-ui/index.html)
- [app.js](file://products/operator-portal/web-ui/app.js)
- [styles.css](file://products/operator-portal/web-ui/styles.css)
- [nginx.conf](file://products/operator-portal/nginx.conf)
- [Dockerfile](file://products/operator-portal/Dockerfile)
- [Makefile](file://products/operator-portal/Makefile)
- [README.md](file://products/operator-portal/README.md)
- [web-ui-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml)
- [web-ui-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-service.yaml)
- [image.mk](file://mk/image.mk)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive "Cited guidance" chips display system for skills.* tools success responses
- Enhanced evidence card rendering with clickable skill citation elements showing title and namespaced ID
- Integrated cited guidance feature into the existing tool evidence system with proper styling and user interaction
- Updated documentation to reflect new skills integration capabilities and enhanced operational visibility

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Two-Column Shell Layout](#two-column-shell-layout)
7. [Role-Gated Audit Trail System](#role-gated-audit-trail-system)
8. [Authentication and Security](#authentication-and-security)
9. [Markdown Rendering System](#markdown-rendering-system)
10. [Real-time Streaming Interface](#real-time-streaming-interface)
11. [Skills Integration and Cited Guidance](#skills-integration-and-cited-guidance)
12. [Deployment Guide](#deployment-guide)
13. [UI Customization](#ui-customization)
14. [Accessibility Features](#accessibility-features)
15. [Browser Compatibility](#browser-compatibility)
16. [Troubleshooting Guide](#troubleshooting-guide)
17. [Conclusion](#conclusion)

## Introduction

The Operator Portal is a modern web-based administrative interface designed for platform administration and monitoring within the Luban AIOPS ecosystem. Built with vanilla JavaScript and HTML/CSS, it provides operators with a sophisticated two-column shell interface featuring a persistent sidebar for navigation and a main content area for interactive operations. The portal serves as a centralized control plane for platform administrators, offering real-time visibility into system status through an interactive chat interface, comprehensive evidence panels for tool execution tracking, configuration management capabilities, and administrative functions necessary for maintaining the AI-powered agent platform infrastructure.

**Updated** The portal has undergone significant enhancements including the addition of "Cited guidance" chips display system that shows matched skills as clickable elements with title and namespaced ID when skills.* tools succeed, providing enhanced operational visibility and traceability for team-owned guidance references.

## Project Structure

The Operator Portal follows a clean, modular architecture with separation of concerns between presentation layer (HTML), styling (CSS), and application logic (JavaScript). The project structure is organized as follows:

```mermaid
graph TB
subgraph "Operator Portal Web UI"
A[index.html] --> B[app.js]
A --> C[styles.css]
D[nginx.conf] --> A
E[Dockerfile] --> A
F[Makefile] --> E
end
subgraph "Kubernetes Deployment"
G[web-ui-deployment.yaml] --> H[web-ui-service.yaml]
H --> I[Service Endpoint]
end
J[Backend Services] --> K[API Gateway]
K --> L[Agent Platform]
K --> M[Identity Broker]
K --> N[Tool Gateway]
I --> K
```

**Diagram sources**
- [index.html](file://products/operator-portal/web-ui/index.html)
- [app.js](file://products/operator-portal/web-ui/app.js)
- [nginx.conf](file://products/operator-portal/nginx.conf)
- [web-ui-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml)

**Section sources**
- [index.html](file://products/operator-portal/web-ui/index.html)
- [app.js](file://products/operator-portal/web-ui/app.js)
- [styles.css](file://products/operator-portal/web-ui/styles.css)

## Core Components

The Operator Portal consists of several key components that work together to provide a comprehensive administrative interface:

### Frontend Architecture
- **Two-Column Shell Layout**: Professional interface with persistent sidebar and main content area
- **Chat-Based Interface**: Modern single-page application with real-time streaming responses
- **Inline Per-Turn Evidence System**: Sophisticated turn-scoped evidence grouping with collapsible groups rendered directly after agent responses
- **Skills Integration**: Enhanced evidence cards with "Cited guidance" chips displaying matched skills when skills.* tools succeed
- **Authentication System**: OIDC integration with automatic token refresh and session management
- **Markdown Renderer**: Comprehensive text formatting with syntax highlighting support
- **Responsive Design**: Dark theme with mobile-first approach and accessibility features

### Backend Integration
- **Streaming API Client**: Real-time communication with backend services via Server-Sent Events
- **Authentication Handler**: Seamless integration with identity broker for secure access
- **Session Management**: Persistent session handling with automatic refresh mechanisms
- **Error Handling**: Comprehensive error management with user-friendly feedback

### Enhanced User Interface
- **Persistent Sidebar**: Branding, identity management, and function navigation
- **User Card System**: Avatar display with initials, username badge, and role information
- **Role-Based Navigation**: Conditional visibility of audit trail based on user roles
- **Mobile Drawer**: Off-canvas navigation for narrow screens with hamburger menu
- **Settings & Debug Panel**: Configuration management and debugging tools

### Skills Evidence Enhancement
- **Cited Guidance Chips**: Visual indicators showing matched skills from successful skills.* tool executions
- **Skill Citation Display**: Clickable elements displaying skill titles and namespaced IDs
- **Evidence Integration**: Seamless integration with existing evidence card system
- **Truncation Handling**: Smart handling of truncated data summaries to avoid partial citations

### Deployment Components
- **Container Image**: Dockerized application using nginxinc/nginx-unprivileged:1.27-alpine for non-root execution
- **Kubernetes Resources**: Deployment and service definitions with enhanced security context
- **Configuration Management**: Environment-specific settings and secrets

**Updated** The interface now includes enhanced skills integration with "Cited guidance" chips that provide visual feedback when skills.* tools successfully execute, showing matched skills as clickable elements with title and namespaced ID for improved operational traceability.

**Section sources**
- [app.js](file://products/operator-portal/web-ui/app.js)
- [Dockerfile](file://products/operator-portal/Dockerfile)
- [web-ui-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml)

## Architecture Overview

The Operator Portal follows a modern single-page application (SPA) architecture built with vanilla JavaScript, providing a responsive and interactive user experience without relying on heavy frameworks.

```mermaid
sequenceDiagram
participant User as "Browser"
participant Portal as "Operator Portal"
participant Nginx as "Nginx Server (Port 8080)"
participant Gateway as "API Gateway"
participant Identity as "Identity Broker"
participant Agent as "Agent Platform"
User->>Portal : Load index.html
Portal->>Nginx : Request static assets (Port 8080)
Nginx-->>Portal : Serve HTML/CSS/JS
Note over Portal : Authentication Flow
Portal->>Gateway : /api/v1/auth/login
Gateway->>Identity : Redirect to OIDC provider
Identity-->>Gateway : Authorization code
Gateway-->>Portal : Access tokens + identity
Note over Portal : Chat & Streaming
User->>Portal : Send prompt
Portal->>Gateway : POST /api/v1/chat/stream
Gateway->>Agent : Forward request
Agent-->>Gateway : Stream events
Gateway-->>Portal : SSE stream
Portal->>User : Render markdown response
Portal->>User : Create inline evidence group
Portal->>User : Update per-turn audit card
Portal->>User : Display cited guidance chips for skills.* tools
```

**Diagram sources**
- [index.html](file://products/operator-portal/web-ui/index.html)
- [app.js](file://products/operator-portal/web-ui/app.js)
- [nginx.conf](file://products/operator-portal/nginx.conf)

The architecture emphasizes simplicity, performance, and maintainability while providing enterprise-grade functionality for platform operations.

## Detailed Component Analysis

### HTML Structure and Layout

The main HTML document defines the semantic structure of the operator portal with a professional two-column shell layout:

- **App Shell**: Grid-based layout with fixed-width sidebar and flexible main content area
- **Sidebar**: Persistent navigation panel with branding, user identity, and function list
- **Main Area**: Content area displaying one function view at a time (chat, settings, audit)
- **Mobile Top Bar**: Hamburger menu and title for narrow screen navigation
- **View Sections**: Separate sections for chat workspace, settings/debug panel, and audit trail

### JavaScript Application Logic

The JavaScript application implements core functionality including:

#### Two-Column Shell Navigation
- **View Management**: Show/hide different views while preserving state and history
- **Sidebar Controls**: Mobile drawer toggle with backdrop and keyboard navigation
- **Active State Management**: Visual indicators for current active view
- **Role-Based Access Control**: Conditional visibility of audit trail based on user roles

#### Enhanced User Identity System
- **User Card Display**: Avatar with initials, username badge, and role information
- **Popup Menu**: User-related actions and information in dropdown menu
- **Login/Logout Actions**: Icon-only buttons with tooltip support
- **Session Persistence**: Secure storage of authentication state in sessionStorage

#### Chat Interface Management
- **Real-time Streaming**: Server-Sent Events for live response updates
- **Message History**: Persistent conversation display with user and agent messages
- **Sticky Smart-scroll**: Intelligent scrolling that respects user reading position during streaming
- **Input Handling**: Keyboard shortcuts and form validation

#### Inline Per-Turn Evidence System
- **Per-turn Evidence Grouping**: Organizes evidence by conversation turns with collapsible groups rendered inline after agent responses
- **Turn-based Organization**: Uses currentTurn object to track active conversation turn with anchor, group, body, summaryLine, counts, entries, and cardMap properties
- **Evidence Turn Management**: Lazy creation of evidence groups on first tool frame with ensureCurrentTurn function
- **Live Status Metrics**: Real-time counters tracking pending, success, error, and denied states with formatCounts function
- **Per-turn Audit Cards**: Comprehensive aggregation of tool executions with metadata display in tabular format
- **Evidence Summary**: Dynamic summary line showing current turn statistics with collapsible details element

#### Skills Integration and Cited Guidance
- **Cited Skills Detection**: Automatic detection of skills.* tool success responses with matched skills data
- **Chip Generation**: Creation of clickable chip elements displaying skill titles and namespaced IDs
- **Evidence Integration**: Seamless integration with existing evidence card system
- **Truncation Handling**: Smart filtering to avoid displaying partial or truncated skill citations
- **Visual Styling**: Professional chip design with proper spacing, borders, and typography

#### Durable Audit Trail System
- **Role-Gated Access**: Audit trail view hidden unless user has auditor or platform-admin roles
- **Filtering Capabilities**: Username, event type, service, and date range filters
- **Pagination Support**: Cursor-based pagination with load more functionality
- **Event Detail View**: Expandable rows showing full event envelope JSON

**Updated** The interface now includes comprehensive skills integration with "Cited guidance" chips that automatically detect and display matched skills from successful skills.* tool executions, providing enhanced operational visibility and traceability for team-owned guidance references.

**Section sources**
- [app.js](file://products/operator-portal/web-ui/app.js)

### CSS Styling System

The styling system provides a comprehensive design foundation with:

#### Design Tokens
- **Dark Theme**: Modern color palette optimized for extended use
- **Typography Scale**: Inter font family with responsive sizing
- **Spacing System**: Consistent margins and padding throughout
- **Animation Effects**: Smooth transitions and loading indicators

#### Two-Column Layout System
- **Grid-Based Shell**: Fixed 230px sidebar with flexible main content area
- **Responsive Breakpoints**: Mobile-first approach with off-canvas drawer below 800px
- **Sidebar Styling**: Professional navigation with hover effects and active states
- **Main Area**: Full-height content area with proper overflow handling

#### Component Styles
- **User Card**: Avatar display with initials, username badge, and role information
- **Navigation Items**: Clean button styling with active state indicators
- **Chat Messages**: Distinct styling for user and agent messages
- **Inline Evidence Groups**: Professional collapsible interface with native browser details element behavior
- **Cited Guidance Chips**: Specialized styling for skill citation chips with proper typography and spacing
- **Audit Trail Table**: Responsive table with sticky headers and expandable detail rows
- **Settings Panel**: Grid-based layout for configuration options
- **Mobile Drawer**: Slide-in navigation with backdrop overlay

#### Accessibility Features
- **High Contrast**: WCAG 2.1 AA compliant color ratios
- **Keyboard Navigation**: Full keyboard operability with visible focus indicators
- **Screen Reader Support**: Semantic HTML and ARIA labels
- **Reduced Motion**: Respects user motion preferences

**Section sources**
- [styles.css](file://products/operator-portal/web-ui/styles.css)

## Two-Column Shell Layout

The Operator Portal features a professional two-column shell layout designed for optimal usability and information density.

### Layout Architecture

The shell layout uses CSS Grid to create a fixed-width sidebar with a flexible main content area:

- **Sidebar Width**: Fixed 230px width providing consistent navigation space
- **Main Area**: Flexible content area that adapts to available screen space
- **Grid Template**: `grid-template-columns: 230px minmax(0, 1fr)` for responsive behavior
- **Full Height**: Both columns span the full viewport height with proper overflow handling

### Sidebar Functionality

The persistent sidebar contains three primary sections:

#### Branding and Identity
- **Logo Display**: "Luban AIOps" branding with accent color styling
- **User Card**: Interactive card showing user avatar, username, and role information
- **Version Information**: Platform version display in footer section

#### Navigation Menu
- **Function List**: Chat, Settings & Debug, and Audit trail navigation items
- **Active State**: Visual indicator showing current active view
- **Stream Indicator**: Pulsing dot showing when chat streaming is active
- **Role-Based Visibility**: Audit trail link hidden unless user has appropriate roles

#### Footer Section
- **User Identity**: Persistent display of authenticated user with login/logout actions
- **Platform Version**: Version information kept in sync with CHANGELOG milestones
- **Auto-positioning**: Uses margin-top:auto to pin footer to bottom of sidebar

### Mobile Responsive Design

For screens below 800px, the layout transforms to a mobile-first approach:

- **Off-Canvas Drawer**: Sidebar slides in from left as overlay when hamburger menu is tapped
- **Top Bar**: Compact header with hamburger button and title
- **Backdrop Overlay**: Semi-transparent background when drawer is open
- **Touch-Friendly**: Larger touch targets and swipe gestures support

**Section sources**
- [index.html:14-77](file://products/operator-portal/web-ui/index.html#L14-L77)
- [styles.css:41-77](file://products/operator-portal/web-ui/styles.css#L41-L77)
- [styles.css:774-837](file://products/operator-portal/web-ui/styles.css#L774-L837)

## Role-Gated Audit Trail System

The Operator Portal implements a comprehensive audit trail system with role-based access control and advanced filtering capabilities.

### Role-Based Access Control

The audit trail view is protected by role-based access control:

- **Required Roles**: Users must have either "auditor" or "platform-admin" roles to access audit trail
- **Client-Side Gating**: Audit trail navigation item hidden unless user has required roles
- **Server-Side Enforcement**: Gateway re-enforces audit:read permission on every request
- **Automatic View Switching**: If user loses required roles, automatically switches back to chat view

### Audit Trail Interface

The audit trail provides comprehensive event inspection capabilities:

#### Filter Toolbar
- **Username Filter**: Search by specific username
- **Event Type Filter**: Filter by event types (tool_invoked, policy_decision, token_exchange, etc.)
- **Service Filter**: Filter by originating service (tool-gateway, platform-gateway, identity-service)
- **Date Range Filters**: Since and until datetime-local inputs for temporal filtering
- **Refresh Button**: Reload current filtered results

#### Event Display
- **Table Format**: Clean tabular display with columns for timestamp, type, service, outcome, actor, and request ID
- **Expandable Details**: Click any row to reveal full event envelope JSON
- **Status Indicators**: Color-coded outcomes with negative outcomes highlighted in red
- **Pagination**: Cursor-based pagination with "Load more" button for large result sets

#### Data Management
- **Lazy Loading**: Events loaded only when audit view is activated
- **State Preservation**: Filter selections and loaded data preserved during navigation
- **Error Handling**: Graceful error display with user-friendly messages
- **Loading States**: Visual feedback during data loading operations

### Security Considerations

The audit trail system implements multiple security layers:

- **Role Verification**: Client-side role checking before rendering audit view
- **Server-Side Validation**: Gateway enforces audit:read permission on all requests
- **Request Context**: Includes x-request-id for traceability
- **Authentication Required**: All audit requests require valid authentication tokens

**Section sources**
- [app.js:27-39](file://products/operator-portal/web-ui/app.js#L27-L39)
- [app.js:232-234](file://products/operator-portal/web-ui/app.js#L232-L234)
- [app.js:403-506](file://products/operator-portal/web-ui/app.js#L403-L506)
- [index.html:124-156](file://products/operator-portal/web-ui/index.html#L124-L156)

## Authentication and Security

The Operator Portal implements comprehensive authentication and security features using OpenID Connect (OIDC) protocol with automatic session management.

### OIDC Integration Flow

The authentication system supports complete OIDC flows:

- **Login Initiation**: Redirect to identity provider with PKCE flow
- **Code Exchange**: Secure authorization code exchange for tokens
- **State Validation**: CSRF protection with state parameter verification
- **Session Storage**: Secure token storage in sessionStorage

### Token Management

Automatic token lifecycle management ensures seamless user experience:

- **Access Token Refresh**: Silent refresh 60 seconds before expiration
- **Refresh Token Handling**: Background renewal of expired sessions
- **Graceful Degradation**: Fallback to cached identity when refresh fails
- **Logout Support**: Complete logout with ID token hint

### Security Context

Enhanced security measures protect against common vulnerabilities:

- **Non-root Execution**: Container runs as unprivileged user (UID 101)
- **Security Context**: Proper Kubernetes security policies applied
- **CORS Configuration**: Strict cross-origin request policies
- **Content Security**: Safe HTML rendering with proper escaping

### Identity Management

Flexible identity handling supports various scenarios:

- **Authenticated Users**: Full access with verified identity
- **Demo Mode**: Local development with simulated identities
- **Group Membership**: Role-based access control integration
- **Custom Claims**: Support for organization-specific identity attributes

### User Interface Enhancements

The authentication system integrates seamlessly with the new UI:

- **User Card Display**: Avatar with initials, username badge, and role information
- **Login/Logout Buttons**: Icon-only buttons with tooltip support
- **Role-Based Navigation**: Conditional visibility of audit trail based on user roles
- **Session Persistence**: Automatic session restoration on page reload

**Section sources**
- [app.js:197-354](file://products/operator-portal/web-ui/app.js#L197-L354)
- [app.js:555-642](file://products/operator-portal/web-ui/app.js#L555-L642)
- [web-ui-deployment.yaml:22-27](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml#L22-L27)

## Markdown Rendering System

The Operator Portal includes a comprehensive markdown rendering engine that transforms plain text into rich, formatted HTML content for display in the chat interface.

### Supported Markdown Features

The renderer supports extensive markdown syntax:

- **Headers**: Six levels of heading hierarchy (h1-h6)
- **Text Formatting**: Bold, italic, strikethrough, and emphasis
- **Lists**: Ordered and unordered lists with nested support
- **Code Blocks**: Syntax-highlighted code with language specification
- **Inline Code**: Monospace formatting for inline code snippets
- **Links**: Hyperlinks with external target support
- **Blockquotes**: Nested quote blocks with visual styling
- **Tables**: Structured data presentation with headers and alignment
- **Horizontal Rules**: Visual separators for content organization

### Security Considerations

The markdown renderer implements multiple security measures:

- **HTML Escaping**: All user input is escaped before processing using escapeHtml function
- **Safe Link Handling**: External links open in new tabs with security attributes
- **XSS Prevention**: No raw HTML injection or script execution
- **Content Sanitization**: Removal of potentially dangerous elements

### Performance Optimization

Efficient rendering ensures smooth user experience:

- **Incremental Processing**: Progressive text updates during streaming
- **DOM Manipulation**: Minimal DOM operations for optimal performance
- **Memory Management**: Proper cleanup of temporary objects
- **String Processing**: Optimized regex patterns for fast parsing

### Styling and Theming

Consistent visual presentation across all rendered content:

- **Theme Integration**: Dark theme with accent colors and proper contrast
- **Code Styling**: Monospace fonts with syntax highlighting support
- **Responsive Design**: Adapts to different screen sizes and orientations
- **Accessibility**: Proper semantic markup for screen readers

**Section sources**
- [app.js:111-177](file://products/operator-portal/web-ui/app.js#L111-L177)
- [styles.css:473-549](file://products/operator-portal/web-ui/styles.css#L473-L549)

## Real-time Streaming Interface

The Operator Portal implements a sophisticated real-time streaming interface using Server-Sent Events (SSE) for live chat responses and tool execution updates.

### Streaming Architecture

The streaming system handles real-time communication efficiently:

- **Server-Sent Events**: Native browser API for server-to-client updates
- **Event Parsing**: Robust JSON event parsing with error handling
- **Buffer Management**: Efficient text buffer handling for large responses
- **Connection Recovery**: Automatic reconnection on network interruptions

### Message Type Handling

Different event types are processed appropriately:

- **Message Delta**: Incremental text updates for streaming responses
- **Tool Calls**: Evidence drawer updates for tool execution via renderToolCall function
- **Tool Results**: Completion notifications with status and data via renderToolResult function
- **Stream Completion**: Finalization signals for response ending

### User Experience Features

Intuitive streaming interface enhances usability:

- **Sticky Smart-scroll**: Intelligent scrolling that respects user reading position
- **Placeholder Handling**: Graceful handling of empty or delayed responses
- **Error Display**: User-friendly error messages for connection issues
- **Loading States**: Visual feedback during streaming operations

### Performance Considerations

Optimized for high-frequency updates:

- **Batch Processing**: Efficient event batching for better performance
- **DOM Updates**: Minimal DOM manipulation for smooth animations
- **Memory Management**: Proper cleanup of streaming resources
- **Network Efficiency**: Connection reuse and request optimization

### Enhanced Streaming Features

The new interface includes additional streaming enhancements:

- **Thinking Indicator**: Animated placeholder shown while agent processes requests
- **Sidebar Pulse**: Visual indicator in sidebar showing active streaming state
- **Turn Scoping**: Each conversation turn maintains its own evidence context
- **Error Recovery**: Graceful handling of streaming errors with user feedback

**Section sources**
- [app.js:925-1050](file://products/operator-portal/web-ui/app.js#L925-L1050)
- [styles.css:330-359](file://products/operator-portal/web-ui/styles.css#L330-L359)

## Skills Integration and Cited Guidance

The Operator Portal now includes comprehensive skills integration with "Cited guidance" chips that provide enhanced operational visibility when skills.* tools successfully execute.

### Cited Guidance System Architecture

The cited guidance system automatically detects and displays matched skills from successful skills.* tool executions:

#### Skill Detection Logic
- **Success Status Check**: Only processes tool results with "success" status
- **Data Summary Validation**: Ensures data_summary exists and is not truncated
- **Tool Type Recognition**: Handles different skills.* tool types (search, list, get)
- **Entry Extraction**: Extracts skill entries based on tool type (matches, skills, or single data)

#### Chip Generation Process
- **Validation Filtering**: Filters out invalid entries without skill_id
- **Title Generation**: Creates user-friendly titles from skill data or falls back to skill_id
- **Element Creation**: Generates clickable chip elements with proper styling
- **Integration**: Seamlessly integrates with existing evidence card system

#### Visual Presentation
- **Chip Design**: Professional chip styling with borders, background, and proper spacing
- **Typography**: Clear title display with monospace font for skill IDs
- **Layout**: Flexbox-based layout with proper wrapping and gaps
- **Responsiveness**: Adapts to different screen sizes and content lengths

### Implementation Details

The cited guidance system is implemented through two key functions:

#### citedSkills Function
- **Input Processing**: Validates payload status and data structure
- **Tool Type Handling**: Processes different skills.* tool types appropriately
- **Data Extraction**: Extracts skill information from various data structures
- **Output Generation**: Returns array of skill objects with id and title

#### renderCitedGuidance Function
- **Conditional Rendering**: Only renders for skills.* tools with valid citations
- **Duplicate Prevention**: Prevents multiple rendering of same evidence card
- **Element Construction**: Builds DOM structure for cited guidance section
- **Styling Application**: Applies proper CSS classes for visual presentation

### User Experience Benefits

The cited guidance system provides several operational benefits:

#### Enhanced Traceability
- **Skill Reference**: Clear indication of which team-owned guidance was used
- **Namespaced IDs**: Precise identification of specific skill versions
- **Visual Feedback**: Immediate recognition of skills usage in tool execution

#### Improved Operational Visibility
- **Quick Reference**: At-a-glance understanding of guidance sources
- **Click-to-Copy**: Easy copying of skill IDs for further investigation
- **Contextual Information**: Title and ID displayed together for clarity

#### Integration with Existing Features
- **Evidence Cards**: Seamless integration with existing evidence system
- **Turn Scoping**: Proper association with conversation turns
- **Status Tracking**: Works alongside existing success/error/denied status indicators

### Styling and Design

The cited guidance chips follow the established design system:

#### Visual Design
- **Color Scheme**: Uses existing design tokens for consistency
- **Typography**: Mix of regular and monospace fonts for readability
- **Spacing**: Proper margins and padding for visual hierarchy
- **Borders**: Subtle borders to distinguish chips from other content

#### Responsive Behavior
- **Flexbox Layout**: Automatic wrapping for multiple chips
- **Text Overflow**: Ellipsis handling for long skill titles
- **Touch Friendly**: Adequate sizing for mobile interaction
- **Screen Reader Support**: Proper ARIA attributes and semantic markup

**Section sources**
- [app.js:750-799](file://products/operator-portal/web-ui/app.js#L750-L799)
- [styles.css:566-604](file://products/operator-portal/web-ui/styles.css#L566-L604)

## Deployment Guide

### Prerequisites

Before deploying the Operator Portal, ensure you have the following prerequisites:

- **Kubernetes Cluster**: Version 1.20 or higher
- **Helm**: Version 3.x for package management
- **kubectl**: Latest stable version configured for your cluster
- **Nginx Ingress Controller**: For external access routing
- **TLS Certificates**: Valid certificates for HTTPS access
- **Identity Provider**: OIDC-compatible identity provider (Keycloak, Auth0, etc.)

### Container Image Build

Build the container image using the provided Makefile:

```bash
cd products/operator-portal
make build
make push
```

### Kubernetes Deployment

Deploy the portal using the provided Kubernetes manifests:

```bash
# Create namespace
kubectl create namespace operator-portal

# Apply deployment
kubectl apply -f shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml

# Apply service
kubectl apply -f shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-service.yaml
```

### Nginx Configuration

The nginx configuration handles static file serving and reverse proxy setup on port 8080:

- **Static Asset Serving**: Optimized delivery of HTML, CSS, and JavaScript files
- **API Proxying**: Reverse proxy to platform gateway for backend communication
- **Streaming Support**: Configured for long-lived connections and SSE streams with proxy_buffering off
- **Security Headers**: Content Security Policy and other security headers
- **Compression**: Gzip compression for reduced bandwidth usage
- **Non-root Execution**: Runs as unprivileged user for enhanced security

### Environment Configuration

Configure environment variables for the portal deployment:

- **API Gateway URL**: Backend API gateway endpoint
- **Authentication Provider**: Identity broker configuration
- **Logging Level**: Debug, info, warning, or error levels
- **Feature Flags**: Enable/disable specific features

**Updated** The deployment now supports the enhanced skills integration with "Cited guidance" chips, providing improved operational visibility for team-owned guidance references. The nginx configuration remains optimized for streaming support and non-root execution.

**Section sources**
- [nginx.conf](file://products/operator-portal/nginx.conf)
- [Dockerfile](file://products/operator-portal/Dockerfile)
- [web-ui-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml)
- [web-ui-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-service.yaml)
- [image.mk](file://mk/image.mk)

## UI Customization

The Operator Portal supports extensive UI customization to match organizational branding and preferences.

### Theme Customization

- **Color Schemes**: Primary, secondary, and accent colors via CSS custom properties
- **Typography**: Font families, sizes, and line heights
- **Layout Options**: Compact, standard, and spacious layouts
- **Dark/Light Mode**: Automatic or manual theme switching

### Branding Elements

- **Logo Integration**: Custom logo placement and sizing
- **Favicon Support**: Custom browser tab icons
- **Page Titles**: Customizable page titles and meta descriptions
- **Watermarking**: Optional watermark overlay for sensitive environments

### Layout Customization

- **Widget Configuration**: Show/hide dashboard widgets
- **Column Layouts**: Adjustable grid layouts for different screen sizes
- **Navigation Structure**: Customizable navigation menus
- **Responsive Breakpoints**: Mobile-first responsive design

### Accessibility Customization

- **High Contrast Mode**: Enhanced contrast for better visibility
- **Screen Reader Support**: ARIA labels and semantic markup
- **Keyboard Navigation**: Full keyboard operability
- **Font Scaling**: Support for increased font sizes

### New Customization Options

The updated interface provides additional customization points:

- **Sidebar Width**: Adjustable sidebar width for different screen densities
- **User Card Layout**: Customizable user card appearance and positioning
- **Navigation Item Styling**: Custom styling for navigation items and active states
- **Mobile Drawer Behavior**: Configurable drawer animation and positioning
- **Cited Guidance Styling**: Customizable chip appearance and behavior for skills integration

**Section sources**
- [styles.css](file://products/operator-portal/web-ui/styles.css)

## Accessibility Features

The Operator Portal is designed with accessibility as a first-class concern, ensuring usability for users with disabilities.

### WCAG Compliance

- **WCAG 2.1 AA Compliance**: Meets Web Content Accessibility Guidelines
- **Semantic HTML**: Proper use of semantic elements and landmarks
- **ARIA Labels**: Comprehensive ARIA attributes for assistive technologies
- **Keyboard Navigation**: Full keyboard operability with visible focus indicators

### Screen Reader Support

- **Descriptive Alt Text**: Meaningful alternative text for images and icons
- **Form Labels**: Properly associated form labels and instructions
- **Error Messages**: Descriptive error messages with suggestions
- **Status Updates**: Live regions for dynamic content updates

### Visual Accessibility

- **Color Contrast**: Minimum 4.5:1 contrast ratio for normal text
- **Text Resizing**: Support for up to 200% text zoom
- **Focus Indicators**: Clear visual focus indicators
- **Reduced Motion**: Respect for user motion preferences

### Cognitive Accessibility

- **Simple Language**: Clear and concise language throughout
- **Consistent Layout**: Predictable navigation and interaction patterns
- **Error Prevention**: Helpful error messages and recovery options
- **Progress Indicators**: Clear feedback for long-running operations

### Enhanced Accessibility Features

The new interface includes additional accessibility improvements:

- **Two-Column Layout**: Proper semantic structure with nav and main landmarks
- **Sidebar Navigation**: Accessible navigation with proper ARIA attributes
- **User Card**: Accessible user identity display with proper labeling
- **Mobile Drawer**: Accessible off-canvas navigation with proper focus management
- **Audit Trail**: Accessible table with proper headers and expandable details
- **Cited Guidance Chips**: Accessible chip elements with proper labeling and keyboard navigation

**Section sources**
- [styles.css](file://products/operator-portal/web-ui/styles.css)
- [index.html](file://products/operator-portal/web-ui/index.html)

## Browser Compatibility

The Operator Portal supports modern web browsers with progressive enhancement for broader compatibility.

### Supported Browsers

- **Chrome**: Version 90+ (recommended)
- **Firefox**: Version 88+
- **Safari**: Version 14+
- **Edge**: Version 90+
- **Mobile Safari**: iOS 14+
- **Android Chrome**: Android 10+

### Feature Support

- **ES6+ JavaScript**: Modern JavaScript features with polyfills
- **CSS Grid and Flexbox**: Flexible layout systems
- **Web APIs**: Fetch API, Local Storage, Service Workers, Server-Sent Events
- **Media Queries**: Responsive design capabilities
- **Canvas API**: Chart and graph rendering

### Polyfills and Fallbacks

- **CoreJS**: JavaScript feature polyfills for older browsers
- **Autoprefixer**: CSS vendor prefixing for cross-browser compatibility
- **Babel Transpilation**: ES6+ to ES5 transpilation when needed
- **Graceful Degradation**: Essential functionality works across all supported browsers

### New Feature Compatibility

The updated interface maintains broad browser compatibility:

- **CSS Grid**: Used for two-column layout with fallbacks for older browsers
- **CSS Custom Properties**: Theme customization with fallback values
- **Modern JavaScript**: ES6+ features with appropriate polyfills
- **Responsive Design**: Mobile-first approach with progressive enhancement
- **Skills Integration**: Cited guidance chips work across all supported browsers

**Section sources**
- [Dockerfile](file://products/operator-portal/Dockerfile)
- [app.js](file://products/operator-portal/web-ui/app.js)

## Troubleshooting Guide

Common issues and their solutions when working with the Operator Portal.

### Connection Issues

**Problem**: Cannot connect to backend services
**Solution**: 
- Verify API gateway URL configuration
- Check network connectivity and firewall rules
- Confirm authentication credentials are valid
- Review nginx configuration for proper routing on port 8080

### Authentication Problems

**Problem**: Login failures or session timeouts
**Solution**:
- Verify identity broker connectivity
- Check token expiration and refresh mechanisms
- Ensure CORS policies allow the portal domain
- Review browser cookie settings and privacy modes

### Performance Issues

**Problem**: Slow dashboard loading or unresponsive interface
**Solution**:
- Check browser developer tools for console errors
- Verify network request timing and response sizes
- Review server-side API performance and database queries
- Optimize image and asset loading strategies

### Deployment Issues

**Problem**: Kubernetes deployment failures
**Solution**:
- Check pod logs for error messages
- Verify resource quotas and limits
- Ensure proper RBAC permissions
- Validate configuration secrets and configmaps
- Confirm non-root execution permissions are properly configured

### Port Configuration Issues

**Problem**: Service not accessible on expected port
**Solution**:
- Verify nginx is listening on port 8080
- Check Kubernetes service port mappings
- Ensure ingress controller routes traffic correctly
- Review firewall rules allowing port 8080

### Streaming Message Issues

**Problem**: Stream completes with no visible text or missing delta events
**Solution**:
- Verify streaming endpoint returns proper event format with 'type' field
- Check that message_delta events contain valid delta content
- Ensure stream completion events are properly handled
- Review browser console for JavaScript errors in streaming logic
- Confirm nginx proxy configuration allows streaming responses

### Two-Column Layout Issues

**Problem**: Sidebar not displaying correctly or main content overlapping
**Solution**:
- Verify CSS Grid template is properly defined with correct column widths
- Check that app-shell class is applied to the root container
- Ensure proper viewport meta tag is present for mobile responsiveness
- Review CSS media queries for mobile breakpoint handling
- Confirm sidebar has proper z-index and positioning styles

### Mobile Drawer Issues

**Problem**: Hamburger menu not working or drawer not appearing on mobile
**Solution**:
- Verify mobile-topbar class is present and styled correctly
- Check that menu-button has proper event listeners attached
- Ensure sidebar-backdrop is positioned correctly with proper z-index
- Review CSS media queries for mobile-specific styles
- Confirm JavaScript drawer toggle functions are properly initialized

### Role-Based Access Issues

**Problem**: Audit trail not visible or access denied despite having correct roles
**Solution**:
- Verify user has auditor or platform-admin roles in identity system
- Check client-side role detection in canViewAudit function
- Ensure server-side audit:read permission is properly enforced
- Review browser console for role detection errors
- Confirm identity normalization is working correctly

### User Card Issues

**Problem**: User avatar not displaying or identity information incorrect
**Solution**:
- Check userInitials function for proper username parsing
- Verify identity payload contains expected fields
- Ensure user card popup menu is properly positioned
- Review CSS for user-card and related styling classes
- Check for JavaScript errors in user identity management

### Sticky Scroll Issues

**Problem**: Auto-scroll not working correctly during streaming
**Solution**:
- Verify chat-main element has proper overflow and height settings
- Check isNearBottom function logic for scroll threshold calculation
- Ensure scrollToBottom function is called appropriately during streaming
- Review CSS for any conflicting overflow or positioning styles

### Skills Integration Issues

**Problem**: Cited guidance chips not appearing for skills.* tools
**Solution**:
- Verify skills.* tools return success status with proper data_summary structure
- Check that data_summary contains skill_id and title fields
- Ensure tool_name starts with "skills." prefix
- Review browser console for JavaScript errors in citedSkills function
- Verify CSS classes are properly applied for chip styling
- Check that _truncated flag is not set in data_summary

### Cited Guidance Display Issues

**Problem**: Cited guidance chips displaying incorrectly or not at all
**Solution**:
- Verify renderCitedGuidance function is being called with proper payload
- Check that evidence card exists and has proper structure
- Ensure CSS classes for cited-guidance, cited-chips, and cited-chip are applied
- Review CSS for proper styling of chip elements
- Check for JavaScript errors in chip generation logic
- Verify skill data contains required fields (skill_id, title)

**Updated** Added troubleshooting guidance for the new skills integration and cited guidance chips feature, including common issues with chip display, skill data validation, and styling problems.

**Section sources**
- [app.js](file://products/operator-portal/web-ui/app.js)

## Conclusion

The Operator Portal provides a comprehensive, accessible, and customizable web interface for platform administration and monitoring within the Luban AIOPS ecosystem. Built with vanilla JavaScript and modern web standards, it delivers enterprise-grade functionality while maintaining simplicity and performance.

**Updated** The recent enhancements include the addition of comprehensive skills integration with "Cited guidance" chips that automatically detect and display matched skills from successful skills.* tool executions, providing enhanced operational visibility and traceability for team-owned guidance references. This feature significantly improves the portal's ability to show operators exactly which team-owned guidance was referenced during tool execution.

Key strengths of the enhanced portal include its modular architecture, extensive customization options, strong accessibility features, seamless integration with backend services, and now comprehensive skills integration capabilities. The deployment process remains streamlined through containerization and Kubernetes-native configurations, making it suitable for both development and production environments.

The enhanced skills integration provides significant improvements in operational traceability, allowing operators to quickly identify which team-owned guidance was used during automated processes. The cited guidance chips offer immediate visual feedback about skill usage while maintaining the existing evidence card system's integrity and performance characteristics.

Future enhancements may include additional dashboard widgets, advanced analytics capabilities, mobile app integration, expanded customization options, enhanced collaboration features, and further improvements to the skills integration system to meet evolving operational requirements.