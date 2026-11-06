(function (root) {
  "use strict";

  function distanceSquared(a, b) {
    return (a.x - b.x) ** 2 + (a.y - b.y) ** 2;
  }

  function pointSegmentDistance(point, start, end) {
    const length = distanceSquared(start, end);
    const t = length ? Math.max(0, Math.min(1,
      ((point.x - start.x) * (end.x - start.x) + (point.y - start.y) * (end.y - start.y)) / length
    )) : 0;
    return distanceSquared(point, {x: start.x + t * (end.x - start.x), y: start.y + t * (end.y - start.y)});
  }

  function intersects(a, b, c, d) {
    const dx = b.x - a.x, dy = b.y - a.y;
    const ex = d.x - c.x, ey = d.y - c.y;
    const denominator = dx * ey - dy * ex;
    if (Math.abs(denominator) < 0.00001) {
      return Math.min(pointSegmentDistance(a, c, d), pointSegmentDistance(b, c, d),
        pointSegmentDistance(c, a, b), pointSegmentDistance(d, a, b)) < 0.01;
    }
    const t = ((c.x - a.x) * ey - (c.y - a.y) * ex) / denominator;
    const u = ((c.x - a.x) * dy - (c.y - a.y) * dx) / denominator;
    if (t < 0 || t > 1 || u < 0 || u > 1) return false;
    // Neighboring conferences can share the same map pixel when zoomed out.
    if (distanceSquared(a, c) < 9 && t * Math.hypot(dx, dy) < 3 && u * Math.hypot(ex, ey) < 3) return false;
    return true;
  }

  function segments(candidate) {
    return [[candidate.anchor, candidate.elbow], [candidate.elbow, candidate.end]];
  }

  function clearOfObstacle(candidate, obstacle, radius) {
    if (obstacle.radius !== undefined) {
      if (distanceSquared(candidate.point, obstacle) < (radius + obstacle.radius + 9) ** 2) return false;
      return segments(candidate).every(function (segment) {
        return pointSegmentDistance(obstacle, segment[0], segment[1]) >= (obstacle.radius + 4) ** 2;
      });
    }
    const left = obstacle.left, right = obstacle.right;
    const top = obstacle.top, bottom = obstacle.bottom;
    const nearest = {x: Math.max(left, Math.min(right, candidate.point.x)),
      y: Math.max(top, Math.min(bottom, candidate.point.y))};
    if (distanceSquared(candidate.point, nearest) < (radius + 6) ** 2) return false;
    const corners = [{x: left - 3, y: top - 3}, {x: right + 3, y: top - 3},
      {x: right + 3, y: bottom + 3}, {x: left - 3, y: bottom + 3}];
    return segments(candidate).every(function (segment) {
      return !corners.some(function (corner, index) {
        return intersects(segment[0], segment[1], corner, corners[(index + 1) % 4]);
      });
    });
  }

  function compatible(left, right, radius) {
    if (distanceSquared(left.point, right.point) < (radius * 2 + 9) ** 2) return false;
    const leftSegments = segments(left), rightSegments = segments(right);
    if (leftSegments.some(function (segment) {
      return pointSegmentDistance(right.point, segment[0], segment[1]) < (radius + 4) ** 2;
    }) || rightSegments.some(function (segment) {
      return pointSegmentDistance(left.point, segment[0], segment[1]) < (radius + 4) ** 2;
    })) return false;
    return !leftSegments.some(function (a) {
      return rightSegments.some(function (b) { return intersects(a[0], a[1], b[0], b[1]); });
    });
  }

  function candidates(entry, obstacles, width, height, radius) {
    const margin = radius + 7, stub = 22;
    const result = [], seen = new Set();
    function add(x, y) {
      if (x < margin || x > width - margin || y < margin || y > height - margin) return;
      const dx = x - entry.anchor.x, dy = y - entry.anchor.y;
      const run = Math.abs(dx) - radius - stub;
      if (run < 12 || Math.abs(dy) < 3 || Math.abs(dy) > run) return;
      const key = Math.round(x) + ":" + Math.round(y);
      if (seen.has(key)) return;
      seen.add(key);
      const side = Math.sign(dx);
      const candidate = {id: entry.id, anchor: entry.anchor, point: {x: x, y: y},
        end: {x: x - side * radius, y: y}, elbow: {x: x - side * (radius + stub), y: y}};
      if (!obstacles.every(function (obstacle) { return clearOfObstacle(candidate, obstacle, radius); })) return;
      const preferredSide = Math.sign(entry.target.x - entry.anchor.x);
      candidate.score = distanceSquared(candidate.point, entry.target) +
        distanceSquared(candidate.point, entry.anchor) * 0.04 + (side === preferredSide ? 0 : 1200);
      result.push(candidate);
    }
    add(entry.target.x, entry.target.y);
    const angles = [-45, -35, -25, -15, -8, 8, 15, 25, 35, 45];
    [-1, 1].forEach(function (side) {
      const room = side > 0 ? width - margin - entry.anchor.x : entry.anchor.x - margin;
      for (let offset = radius + stub + 14; offset <= room; offset += 12) {
        angles.forEach(function (angle) {
          add(entry.anchor.x + side * offset,
            entry.anchor.y + Math.tan(angle * Math.PI / 180) * (offset - radius - stub));
        });
      }
    });
    result.sort(function (left, right) { return left.score - right.score; });
    return result;
  }

  function place(entries, obstacles, width, height, radius) {
    const options = entries.map(function (entry) { return candidates(entry, obstacles, width, height, radius); });
    if (options.some(function (list) { return !list.length; })) return null;
    let visited = 0;
    const chosen = [];
    function search(remaining) {
      if (!remaining.length) return true;
      if (visited > 40000) return false;
      let next, available;
      for (const index of remaining) {
        const valid = options[index].filter(function (candidate) {
          return chosen.every(function (other) { return compatible(candidate, other, radius); });
        });
        if (!valid.length) return false;
        if (!available || valid.length < available.length) { next = index; available = valid; }
      }
      const rest = remaining.filter(function (index) { return index !== next; });
      for (const candidate of available) {
        visited += 1;
        chosen.push(candidate);
        if (search(rest)) return true;
        chosen.pop();
        if (visited > 40000) return false;
      }
      return false;
    }
    return search(entries.map(function (_, index) { return index; })) ? chosen : null;
  }

  root.RecordingMapLayout = {place: place};
})(typeof window === "undefined" ? globalThis : window);
