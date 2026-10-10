/* EA Dubai Community — register, share a view, render the wall.
   All user-supplied text reaches the DOM via textContent only. */

(function () {
  "use strict";

  var LS_EMAIL = "eadc_email";
  var LS_NAME = "eadc_name";
  var MAX_TEXT = 500;

  var registerForm = document.getElementById("register-form");
  var registerError = document.getElementById("register-error");
  var registerNote = document.getElementById("register-note");
  var composerCard = document.getElementById("composer-card");
  var composerWho = document.getElementById("composer-who");
  var testimonyForm = document.getElementById("testimony-form");
  var testimonyText = document.getElementById("testimony-text");
  var testimonyError = document.getElementById("testimony-error");
  var testimonyNote = document.getElementById("testimony-note");
  var charCount = document.getElementById("char-count");
  var counter = document.querySelector(".counter");
  var wall = document.getElementById("wall");
  var wallCount = document.getElementById("wall-count");

  var memberEmail = "";

  function show(el, msg) {
    el.textContent = msg;
    el.hidden = false;
  }

  function hide(el) {
    el.hidden = true;
    el.textContent = "";
  }

  function api(path, options) {
    return fetch(path, options).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          throw new Error(data.error || "Something went wrong.");
        }
        return data;
      });
    });
  }

  function postJSON(path, payload) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  function unlockComposer(member, returning) {
    memberEmail = document.getElementById("reg-email").value.trim();
    var who = member.name;
    var role = [member.title, member.organization]
      .filter(function (s) {
        return s;
      })
      .join(" · ");
    composerWho.textContent = "Signed in as " + who + (role ? " — " + role : "");
    composerCard.hidden = false;
    if (returning) {
      show(registerNote, "Welcome back! Your details are already registered — share or update your view below.");
    } else {
      show(registerNote, "You're registered — share your view below.");
    }
  }

  registerForm.addEventListener("submit", function (event) {
    event.preventDefault();
    hide(registerError);
    hide(registerNote);
    var payload = {
      name: document.getElementById("reg-name").value,
      email: document.getElementById("reg-email").value,
      title: document.getElementById("reg-title").value,
      organization: document.getElementById("reg-org").value,
    };
    var button = registerForm.querySelector("button");
    button.disabled = true;
    postJSON("/api/members", payload)
      .then(function (data) {
        try {
          localStorage.setItem(LS_EMAIL, payload.email.trim().toLowerCase());
          localStorage.setItem(LS_NAME, payload.name.trim());
        } catch (e) {
          /* private mode — prefill is best-effort */
        }
        unlockComposer(data.member, data.returning);
      })
      .catch(function (err) {
        show(registerError, err.message);
      })
      .finally(function () {
        button.disabled = false;
      });
  });

  testimonyText.addEventListener("input", function () {
    var len = testimonyText.value.length;
    charCount.textContent = String(len);
    counter.classList.toggle("limit", len >= MAX_TEXT);
  });

  testimonyForm.addEventListener("submit", function (event) {
    event.preventDefault();
    hide(testimonyError);
    hide(testimonyNote);
    var button = testimonyForm.querySelector("button");
    button.disabled = true;
    postJSON("/api/testimonies", {
      email: memberEmail || localStorage.getItem(LS_EMAIL) || "",
      text: testimonyText.value,
    })
      .then(function () {
        testimonyText.value = "";
        charCount.textContent = "0";
        counter.classList.remove("limit");
        show(testimonyNote, "Your view is published on the wall below.");
        loadWall();
      })
      .catch(function (err) {
        show(testimonyError, err.message);
      })
      .finally(function () {
        button.disabled = false;
      });
  });

  function formatDate(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) {
      return iso;
    }
    return d.toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }

  function renderTestimonies(testimonies) {
    while (wall.firstChild) {
      wall.removeChild(wall.firstChild);
    }
    if (testimonies.length === 0) {
      var empty = document.createElement("p");
      empty.className = "wall-empty";
      empty.textContent = "No views shared yet — register above and be the first.";
      wall.appendChild(empty);
      return;
    }
    testimonies.forEach(function (t) {
      var card = document.createElement("article");
      card.className = "testimony-card";

      var text = document.createElement("p");
      text.className = "testimony-text";
      text.textContent = t.text;
      card.appendChild(text);

      var meta = document.createElement("p");
      meta.className = "testimony-meta";

      var author = document.createElement("span");
      author.className = "testimony-author";
      author.textContent = t.name;
      meta.appendChild(author);

      var role = [t.title, t.organization]
        .filter(function (s) {
          return s;
        })
        .join(" · ");
      if (role) {
        meta.appendChild(document.createTextNode(" — " + role));
      }

      var date = document.createElement("span");
      date.className = "testimony-date";
      date.textContent = formatDate(t.submitted_at);
      meta.appendChild(date);

      card.appendChild(meta);
      wall.appendChild(card);
    });
  }

  function loadWall() {
    return api("/api/testimonies")
      .then(function (data) {
        if (data.count === 0) {
          wallCount.textContent = "No architects have shared their view yet.";
        } else if (data.count === 1) {
          wallCount.textContent = "1 architect has shared their view";
        } else {
          wallCount.textContent = data.count + " architects have shared their view";
        }
        renderTestimonies(data.testimonies);
      })
      .catch(function () {
        wallCount.textContent = "Could not load views right now.";
      });
  }

  // Returning visitors: prefill registration from localStorage.
  try {
    var savedEmail = localStorage.getItem(LS_EMAIL);
    var savedName = localStorage.getItem(LS_NAME);
    if (savedEmail) {
      document.getElementById("reg-email").value = savedEmail;
    }
    if (savedName) {
      document.getElementById("reg-name").value = savedName;
    }
  } catch (e) {
    /* localStorage unavailable — fine */
  }

  loadWall();
})();
