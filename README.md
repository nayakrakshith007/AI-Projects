<div align="center">

<img src="job-radar/docs/storyboard/hero.svg" alt="Job Radar" width="100%">

</div>

# AI Projects

Hands-on AI and data projects, built end to end: design decisions written down, tests included, nothing hidden behind a demo.

| Project | In one line | Stack |
|---|---|---|
| **[Job Radar](job-radar/)** | A free, no-LLM pipeline that reads about 200 job sources every morning and turns them into a dashboard | Python, Playwright, JobSpy, 354 offline tests |

---

## Job Radar in six frames

> A storyboard of the project: the problem, the idea, what runs at 08:30, how it stays trustworthy, what you see, and the proof.

<img src="job-radar/docs/storyboard/frame-1.svg" alt="Frame 1: the problem" width="100%">
<img src="job-radar/docs/storyboard/frame-2.svg" alt="Frame 2: the idea" width="100%">
<img src="job-radar/docs/storyboard/frame-3.svg" alt="Frame 3: the morning run" width="100%">
<img src="job-radar/docs/storyboard/frame-4.svg" alt="Frame 4: trust" width="100%">
<img src="job-radar/docs/storyboard/frame-5.svg" alt="Frame 5: the payoff" width="100%">
<img src="job-radar/docs/storyboard/frame-6.svg" alt="Frame 6: the proof" width="100%">

### The result, on invented demo data

<img src="job-radar/docs/images/dashboard.png" alt="Analytics dashboard built from invented demo data" width="100%">

*Try it: `python job-radar/demo/make_demo.py`, then open `job-radar/demo/output/Dashboard.html`. The repository ships no scraped data.*

### Where to go next

- **[Full project README](job-radar/README.md)**: architecture diagram, reliability, layout, how to run.
- **[Engineering decisions](job-radar/docs/engineering-decisions.md)**: twelve choices, each with the reason and the options that were rejected.
- **[Product requirements](job-radar/docs/PRD-job-radar-v3.md)** and **[how each site is read](job-radar/docs/ARCHITECTURE-sources.md)**.

### Responsible use

Personal, low-volume use. No logins, no CAPTCHA bypass, a polite request rate. Check each site's terms before you use it.

---

By [Rakshith Nayak](https://github.com/nayakrakshith007). MIT licence.
