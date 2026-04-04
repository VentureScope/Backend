# Backend Data Integration Requirements: VentureScope

This document outlines the structured JSON format, suggested API endpoints, and required data fields for the screens provided in the VentureScope platform.

---

## 1. Dashboard View ({{DATA:IMAGE:IMAGE_6}})
**Endpoint:** `GET /api/v1/dashboard/summary`

### JSON Structure
```json
{
  "user": {
    "name": "Alex Sterling",
    "tier": "GOLD TIER MEMBER",
    "avatar_url": "..."
  },
  "readiness_score": {
    "score": 84,
    "percentile": 82
  },
  "ai_insight": {
    "target_role": "Senior DevOps",
    "alignment_percentage": 92,
    "message": "Your skill alignment for Senior DevOps roles is 92%. Check the gaps now."
  },
  "active_module": {
    "title": "Advanced ARIMA Modeling",
    "description": "Mastering Time Series Analysis",
    "progress": 62
  },
  "advisor_preview": {
    "placeholder": "How can I negotiate my salary?"
  },
  "resume_status": {
    "version": "4.2",
    "ats_match_percentage": 92
  },
  "market_trends": {
    "title": "Market Trends",
    "context": "Full-Stack Dev Demand",
    "growth_rate": "+12%",
    "data_points": [
      {"month": "FEB", "value": 30},
      {"month": "MAR", "value": 45},
      {"month": "APR", "value": 35},
      {"month": "MAY", "value": 60},
      {"month": "JUN", "value": 75},
      {"month": "JUL", "value": 65},
      {"month": "AUG", "value": 85}
    ],
    "tags": ["REACT", "NODE.JS"]
  },
  "recent_activity": [
    {
      "type": "sync",
      "message": "Synced Semester 4 Grades",
      "timestamp": "3 HOURS AGO",
      "tag": "Academic Hub"
    },
    {
      "type": "update",
      "message": "Updated Resume keyword: Python",
      "timestamp": "YESTERDAY",
      "tag": "Resume Builder"
    }
  ],
  "suggested_actions": [
    {
      "title": "Update LinkedIn Certifications",
      "description": "Your new certificates aren't reflected in your public profile yet."
    },
    {
      "title": "Quick Skill Test: AWS",
      "description": "Validate your cloud knowledge to boost match score by +4%."
    }
  ]
}
```

---

## 2. AI Advisor Chat ({{DATA:IMAGE:IMAGE_4}})
**Endpoint:** `GET /api/v1/advisor/conversation` | `POST /api/v1/advisor/query`

### JSON Structure
```json
{
  "match_card": {
    "score": 84,
    "skills_alignment": 92,
    "market_reach": 68
  },
  "chat_history": [
    {
      "sender": "ai",
      "text": "Hello, David. I've analyzed your current career trajectory...",
      "source": "LinkedIn Local Market Trends - Ethiopia Q3"
    },
    {
      "sender": "user",
      "text": "I want to target a Senior DevOps role at a multinational company..."
    },
    {
      "sender": "ai",
      "type": "analysis_result",
      "title": "GitHub Analysis Results",
      "points": [
        {"status": "missing", "text": "Missing Infrastructure as Code (IaC)..."},
        {"status": "success", "text": "Strong CI/CD Patterns..."}
      ],
      "sources": [
        {"name": "github.com/d-alemu/nexus-flow", "type": "link"},
        {"name": "Job_Desc_Senior_DevOps_Safaricom.pdf", "type": "pdf"}
      ]
    }
  ],
  "quick_actions": [
    "How do I improve my GitHub for DevOps?",
    "Compare my profile to Senior Architect X",
    "Check salary benchmarks in Addis Ababa"
  ]
}
```

---

## 3. Data Onboarding Hub ({{DATA:IMAGE:IMAGE_5}})
**Endpoint:** `GET /api/v1/onboarding/status`

### JSON Structure
```json
{
  "integrations": [
    {
      "platform": "GitHub",
      "status": "CONNECTED",
      "stats": {
        "repos_synced": 5,
        "commits": 142,
        "languages": 3
      },
      "last_synced": "Oct 24, 2024 • 14:02 PM"
    }
  ],
  "academic_status": {
    "latest_batch": "Semester 4 Grades Processed",
    "gpa": 3.82,
    "max_gpa": 4.0,
    "last_extraction": "2 hours ago"
  },
  "process_steps": [
    {"step": "01", "name": "Connect Portal", "status": "complete"},
    {"step": "02", "name": "Data Scrubbing", "status": "active"},
    {"step": "03", "name": "Profile Scoring", "status": "pending"}
  ]
}
```

---

## 4. Skill Intelligence / Profile ({{DATA:IMAGE:IMAGE_7}})
**Endpoint:** `GET /api/v1/profile/skills`

### JSON Structure
```json
{
  "user_profile": {
    "name": "Alexander Sterling",
    "title": "Senior Strategic Consultant",
    "location": "London, UK",
    "email": "a.sterling@venturescope.ai",
    "timezone": "GMT +1 (London)"
  },
  "career_interests": ["FinTech Strategy", "AI Governance", "VC Operations", "B2B SaaS"],
  "skill_matrix": [
    {
      "category": "STRATEGIC PLANNING",
      "level": "Expert",
      "proficiency": 94,
      "growth": "+2.4%"
    },
    {
      "category": "DATA VISUALIZATION",
      "level": "Advanced",
      "proficiency": 72,
      "status": "Gap Found"
    },
    {
      "category": "PRODUCT MARKETING",
      "level": "Intermediate",
      "proficiency": 58,
      "status": "Steady"
    },
    {
      "category": "STAKEHOLDER MGMT",
      "level": "Elite",
      "proficiency": 98,
      "status": "Top 1%"
    }
  ]
}
```

---

## 5. Market Trends & Forecasting ({{DATA:IMAGE:IMAGE_8}})
**Endpoint:** `GET /api/v1/market/trends?region=ethiopia`

### JSON Structure
```json
{
  "forecast": {
    "version": "FR5.5",
    "chart_data": [
      {"month": "FEB", "value": 40},
      {"month": "MAR", "value": 50},
      {"month": "APR", "value": 55},
      {"month": "MAY", "value": 65},
      {"month": "JUN", "value": 80, "is_forecast": true},
      {"month": "JUL", "value": 85, "is_forecast": true},
      {"month": "AUG", "value": 90, "is_forecast": true}
    ]
  },
  "in_demand_skills": [
    {"skill": "Go (Golang)", "match": 89},
    {"skill": "React / Next.js", "match": 78},
    {"skill": "System Design", "match": 64},
    {"skill": "Data Engineering", "match": 52}
  ],
  "top_hiring_companies": [
    {"name": "Safaricom Ethiopia", "sector": "Telecommunications", "count": 342},
    {"name": "Ethio Telecom", "sector": "Infrastructure", "count": 218},
    {"name": "CBE Tech Hub", "sector": "FinTech", "count": 156}
  ],
  "emerging_trends": [
    {
      "title": "FinTech Scalability",
      "description": "Surge in digital wallet integration skills in Addis Ababa."
    },
    {
      "title": "Cloud Migration",
      "description": "Azure and AWS certifications are currently +40% year-on-year."
    }
  ]
}
```

---

## 6. Adaptive Career Roadmap / Learning Path ({{DATA:IMAGE:IMAGE_3}})
**Endpoint:** `GET /api/v1/learning/roadmap`

### JSON Structure
```json
{
  "current_readiness": {
    "score": 75,
    "target_rank": "Senior Rank"
  },
  "roadmap": [
    {
      "id": "ml-arch",
      "title": "Foundational ML Architecture",
      "status": "COMPLETED",
      "date": "Oct 2023",
      "tags": ["Scikit-Learn", "Pandas"]
    },
    {
      "id": "arima",
      "title": "Advanced ARIMA Modeling",
      "status": "ACTIVE FOCUS",
      "progress": 62,
      "due_date": "Friday, Nov 24"
    }
  ],
  "market_fit_score": {
    "score": 84,
    "technical_match": 92,
    "leadership_index": 68
  },
  "gaps_detected": ["MLOps", "System Design"],
  "curated_credentials": [
    {
      "provider": "AWS",
      "title": "Certified Machine Learning",
      "rank": "SPECIALTY RANK"
    },
    {
      "provider": "Google",
      "title": "Professional ML Engineer",
      "rank": "CLOUD MASTERY"
    }
  ]
}
```

---

## 7. Resume Builder ({{DATA:IMAGE:IMAGE_2}})
**Endpoint:** `GET /api/v1/resume/details` | `POST /api/v1/resume/regenerate`

### JSON Structure
```json
{
  "profile_intelligence": {
    "github": { "status": "CONNECTED", "repos": 12, "commits": 480 },
    "student_sync": { "gpa": "3.9/4.0", "status": "HONOURS" }
  },
  "ats_scoring": {
    "score": 88,
    "missing_keywords": ["Stakeholder Management"],
    "quantifiable_results_improvement": 40
  },
  "summary": {
    "text": "Senior Product Designer with 6+ years of experience...",
    "regenerate_available": true
  },
  "skill_matrix": [
    { "skill": "React.js", "matched": true },
    { "skill": "Tailwind CSS", "matched": true },
    { "skill": "Data Visualization", "matched": false }
  ],
  "experience": [
    {
      "role": "Lead Designer",
      "company": "FinSphere",
      "duration": "2021 - Present",
      "bullets": [
        "Architected the \"Aura\" Design System used by 12+ internal teams.",
        "Optimized dashboard load times by 60% through asset management."
      ]
    }
  ]
}
```

---

## 8. Global Data Hub / Workforce Analytics ({{DATA:IMAGE:IMAGE_1}})
**Endpoint:** `GET /api/v1/workforce/global-stats`

### JSON Structure
```json
{
  "team_competency": {
    "overall": 84.2,
    "yoy_trend": "+3.4%",
    "categories": {
      "cognitive": 92,
      "technical": 74,
      "leadership": 86
    }
  },
  "skill_heatmap": {
    "departments": ["Engineering", "Marketing", "Product", "Sales"],
    "skills": ["AI/ML", "CLOUD", "DATA", "UX", "AGILE"],
    "values": [
      [9.2, 7.4, 5.1, 2.1, 8.5],
      [1.5, 0.8, 6.3, 8.9, 4.2]
    ]
  },
  "upskilling_recommendations": [
    {
      "priority": "Urgent",
      "title": "AI Proficiency Gap",
      "action": "Action"
    },
    {
      "priority": "Recommended",
      "title": "Cloud Certifications",
      "action": "Deploy"
    }
  ],
  "predictive_analytics": {
    "churn_risk": "14.2%",
    "upskilling_roi": "3.2x",
    "time_to_competency": "4.2mo"
  }
}
```