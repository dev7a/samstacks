---
title: samstacks
toc: false
---

<div class="hero-section" id="hero-parallax">
  <div class="hero-content">
    <p class="hero-subtitle">Declarative infrastructure orchestration for AWS SAM deployments.    
    <div class="hero-cta">
      <a href="/samstacks/docs/quickstart" class="hero-button hero-button-primary">Get Started</a>
      <a href="/samstacks/docs" class="hero-button hero-button-secondary">Documentation</a>
    </div>
  </div>
</div>

<script>
// Enhanced parallax scrolling effect with debugging
(function() {
  console.log('Parallax script loading...');
  
  // Wait for DOM to be ready
  function initParallax() {
    const hero = document.getElementById('hero-parallax');
    if (!hero) {
      console.log('Hero element not found');
      return;
    }
    
    console.log('Hero element found, initializing parallax...');
    
    // Check if user prefers reduced motion
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion) {
      console.log('Reduced motion preferred, skipping parallax');
      return;
    }
    
    console.log('Parallax conditions met, setting up scroll listener...');
    
    let ticking = false;
    
    function updateParallax() {
      const scrolled = window.pageYOffset;
      const heroRect = hero.getBoundingClientRect();
      const heroTop = heroRect.top + scrolled;
      const heroHeight = heroRect.height;
      
      // Calculate parallax effect
      const parallaxSpeed = 0.3; // Slower for more subtle effect
      const yPos = scrolled * parallaxSpeed;
      
      // Apply the parallax effect
      const newPosition = `center ${-yPos}px`;
      hero.style.backgroundPosition = newPosition;
      
      // Debug output (remove in production)
      if (scrolled % 50 === 0) { // Log every 50px of scroll
        console.log(`Scroll: ${scrolled}px, BG Position: ${newPosition}`);
      }
      
      ticking = false;
    }
    
    function requestTick() {
      if (!ticking) {
        requestAnimationFrame(updateParallax);
        ticking = true;
      }
    }
    
    // Set initial background position
    hero.style.backgroundPosition = 'center 0px';
    console.log('Initial background position set');
    
    // Add scroll listener
    window.addEventListener('scroll', requestTick, { passive: true });
    console.log('Scroll listener added');
    
    // Test the function immediately
    updateParallax();
    
    // Cleanup on page unload
    window.addEventListener('beforeunload', function() {
      window.removeEventListener('scroll', requestTick);
      console.log('Parallax cleanup completed');
    });
  }
  
  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initParallax);
  } else {
    initParallax();
  }
})();
</script>

**samstacks** is a declarative infrastructure orchestration tool for AWS SAM deployments. It enables teams to define multi-stack deployment pipelines using familiar GitHub Actions syntax with automatic dependency resolution.

## Get Started

{{< cards >}}
  {{< card link="docs" title="Documentation" icon="book-open" >}}
  {{< card link="docs/quickstart" title="Quickstart" icon="play" >}}
  {{< card link="docs/examples" title="Examples" icon="code" >}}
{{< /cards >}}

## Key Capabilities

- **Declarative pipeline configuration** - Define deployment sequences using YAML manifests
- **GitHub Actions compatibility** - Leverage familiar workflow syntax and expressions
- **Native AWS SAM integration** - First-class support for SAM templates and configurations  
- **Intelligent dependency resolution** - Automatic stack ordering based on output dependencies
- **Multi-environment deployments** - Parameterized configuration for development lifecycle

## Quick Example

```yaml
pipeline_name: Deploy Application
pipeline_description: Multi-stack deployment pipeline

stacks:
  - id: vpc-stack
    dir: ./infrastructure/vpc
    
  - id: app-stack
    dir: ./application/app
    params:
      VpcId: ${{ stacks.vpc-stack.outputs.VpcId }}
      SubnetIds: ${{ stacks.vpc-stack.outputs.PrivateSubnetIds }}
```

For more information, visit the [documentation](/samstacks/docs).
