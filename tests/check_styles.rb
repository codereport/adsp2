# frozen_string_literal: true

# Match the Ruby Sass compiler used by GitHub Pages, independently of the
# newer Jekyll/Dart Sass gems used for local development.
gem "sass", "3.7.4"
require "sass"

root = File.expand_path("..", __dir__)
source = File.read(File.join(root, "assets/css/main.scss"))
source = source.sub(/\A---[ \t]*\r?\n.*?^---[ \t]*\r?\n/m, "")

css = Sass.compile(source, :syntax => :scss,
                           :load_paths => [File.join(root, "_sass")],
                           :style => :compact, :cache => false)

# Ruby Sass can report success while passing unsupported module directives
# through to CSS. Check that the theme actually made it into the output.
abort "Uncompiled Sass module directive in main.css" if css.match?(/@(use|forward)\b/)

selectors = [".site-header", ".site-header .avatar", ".content", "#post-nav", ".fa-bars:before"]
selectors.each do |selector|
  rule = /(?:\A|\})\s*[^{}]*#{Regexp.escape(selector)}(?=[\s,{.:#>+~\[])\s*[^{}]*\{/
  abort "Missing theme selector #{selector} in main.css" unless css.match?(rule)
end

puts "GitHub Pages Sass #{Sass::VERSION}: theme CSS compiled successfully (#{css.bytesize} bytes)"
