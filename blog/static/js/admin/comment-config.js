(function () {
  function updateCommentFields() {
    var select = document.getElementById("id_comment_system");
    if (!select) return;

    var providers = ["waline", "gitalk", "twikoo", "giscus"];
    providers.forEach(function (provider) {
      var visible = provider === select.value;
      document.querySelectorAll("[id^=id_" + provider + "_]").forEach(function (input) {
        var row = input.closest(".form-row");
        if (row) {
          row.dataset.commentProviderHidden = visible ? "false" : "true";
          row.hidden = !visible;
        }
      });
    });
    document.dispatchEvent(new CustomEvent("admin:comment-provider-change"));
  }

  document.addEventListener("DOMContentLoaded", function () {
    var select = document.getElementById("id_comment_system");
    if (!select) return;
    select.addEventListener("change", updateCommentFields);
    updateCommentFields();
  });
})();
