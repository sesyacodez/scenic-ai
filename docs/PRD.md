Product Requirements Document (PRD)
ScenicAI – AI-Powered Scenic Walk Route Generator (Demo)
1. Product Overview

Product Name: ScenicAI
Type: Web Application (Demo)
Core Concept:
An AI agent that generates personalized scenic walking routes based on user location, duration, and aesthetic preferences.

The system combines:

Geolocation data

Mapping/routing APIs

Scenic heuristic scoring

An AI agent built using LangChain + LangGraph

The AI agent interprets user intent, adjusts route scoring weights, selects the optimal route, and explains the reasoning behind the choice.

2. Problem Statement

Most mapping applications (e.g., Google Maps, Apple Maps) optimize routes for:

Speed

Distance

Traffic efficiency

They do not optimize for:

Scenic beauty

Quietness

Proximity to nature

Emotional intent (romantic, calming, reflective walk)

Users who want enjoyable walking experiences must manually search for parks or landmarks.

There is no agentic system that:

Understands subjective scenic preferences

Dynamically adjusts routing weights

Explains its reasoning transparently

3. Goals
Primary Goal

Build a demo AI agent that:

Uses the user’s real-time location

Accepts customizable walking preferences

Generates multiple candidate routes

Scores them based on scenic heuristics

Returns the most scenic route

Explains the selection reasoning

Secondary Goals

Demonstrate LangGraph agent orchestration

Showcase tool calling in LangChain

Maintain structured output to avoid hallucinations

Create a clean, modern UI

4. Non-Goals (Important)

Not a production-scale routing engine

Not replacing full-scale mapping apps

No real-time traffic optimization

No large-scale dataset training

No ML model training

This is an intelligent orchestration demo.

5. Target Users
Primary:

Urban walkers

Students

Tourists

People wanting mindful walks

Demo Audience:

Recruiters

AI engineers

Technical interviewers

6. User Stories
US-1: Basic Scenic Route

As a user,
I want to enter my desired walk duration,
So that I can receive a scenic walking route starting from my location.

US-2: Preference-Based Customization

As a user,
I want to select preferences like “nature,” “water,” or “historic,”
So that the route matches my aesthetic intention.

US-3: Conversational Refinement

As a user,
I want to say “make it shorter” or “more water,”
So that the AI agent adjusts the route without re-entering all parameters.

US-4: Explanation Transparency

As a user,
I want to understand why this route was selected,
So that I trust the system’s decision.

7. Functional Requirements
7.1 Geolocation

Detect user location via browser

Fallback: manual location input

7.2 Route Generation

The system must:

Generate 3–5 alternative walking routes

Use a mapping API (e.g., Mapbox or OpenStreetMap data)

Retrieve route geometry (GeoJSON)

7.3 Scenic Scoring Engine

Each route must be scored using weighted criteria:

Example components:

Proximity to parks

Proximity to water bodies

Landmark density

Road type (avoid highways)

Elevation variation (optional)

Scenic score formula:

Scenic Score =
    w1 * nature_score +
    w2 * water_score +
    w3 * landmark_score +
    w4 * quietness_score

Weights are dynamically adjusted by the AI agent.

7.4 AI Agent (LangChain + LangGraph)

The AI agent must:

Parse user input (natural language)

Convert it into structured constraints

Adjust scenic weights

Call routing and scoring tools

Rank routes

Generate explanation

Agent Workflow (LangGraph)

Nodes:

Intent Parsing Node (LLM)

Constraint Structuring Node

Route Tool Node

Scenic Scoring Tool

Route Ranking Node

Explanation Generation Node

7.5 Conversational Updates

The agent must support:

“Make it shorter”

“More nature”

“Avoid busy roads”

Conversation state must persist.

8. Non-Functional Requirements

Response time under 5 seconds

Structured LLM output (JSON schema enforced)

No hallucinated geographic data

Mobile-responsive UI

Clean error handling

9. Technical Architecture
Frontend

Next.js

TailwindCSS

Map visualization (Mapbox GL)

Backend

FastAPI

LangChain

LangGraph

Routing API (Mapbox / OpenStreetMap-based service)

Data Flow
User → Frontend
        ↓
Backend API
        ↓
LangGraph Agent
        ↓
Route Tool → Scenic Scoring
        ↓
Selected Route + Explanation
        ↓
Frontend Map Render
10. Risks
Risk	            Mitigation
Geo API complexity	Build deterministic version first
LLM hallucination	Use structured outputs only
Overengineering	Keep demo scope tight
Slow routing API	Limit alternate routes
11. MVP Definition

The MVP is complete when:

User location detected

Duration input works

3 route alternatives generated

Scenic scoring applied

Best route displayed on map

AI-generated explanation shown

Basic conversational refinement works

12. Success Metrics (Demo-Oriented)

Agent correctly adjusts route weights

Scenic route differs meaningfully from fastest route

LLM output matches schema

System feels intelligent and responsive

13. Future Extensions

Real-time weather-based scenic adjustment

Sunset/sunrise path optimization

Crowd density integration

Mood-based recommendations

User scenic history learning