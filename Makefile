.PHONY: all clean ttf web pack

NAME=AmiriNext
TAG=$(shell git describe --tags --abbrev=0)
VERSION=$(TAG:v%=%)

SRC=sources
BUILDDIR=build
SCRIPTSDIR=scripts
FONTSDIR=fonts
DOC=documentation
FONTS=$(NAME)-Regular $(NAME)-Bold $(NAME)Quran
DIST=$(NAME)-$(VERSION)

BUILD=${SCRIPTSDIR}/build.py
MAKEQURAN=${SCRIPTSDIR}/mkquran.py
PY ?= python

TTF=$(FONTS:%=${FONTSDIR}/%.ttf)
HTML=$(DOC)/Documentation-Arabic.html
FEA=$(wildcard $(SRC)/*.fea)

export SOURCE_DATE_EPOCH ?= 0

all: ttf

ttf: $(TTF)
doc: $(HTML)

$(BUILDDIR)/$(NAME).designspace: $(SRC)/$(NAME).glyphspackage
	@echo "   UFO	$@"
	@glyphs2ufo --minimal --generate-GDEF --output-dir=$(BUILDDIR) $<

$(BUILDDIR)/%.ufo: $(BUILDDIR)/$(NAME).designspace
	@echo "   UFO	$@"

${FONTSDIR}/$(NAME)Quran.ttf: $(BUILDDIR)/$(NAME)-Regular.ufo $(SRC)/$(NAME).fea $(FEA) $(BUILD)
	@echo "   GEN	$@"
	@$(PY) $(BUILD) --input $< --output $@ --features=$(SRC)/$(NAME).fea --version $(VERSION) --quran

${FONTSDIR}/$(NAME)-Regular.ttf: $(BUILDDIR)/$(NAME)-Regular.ufo $(SRC)/$(NAME).fea $(FEA) $(BUILD)
	@echo "   GEN	$@"
	@$(PY) $(BUILD) --input $< --output $@ --features=$(SRC)/$(NAME).fea --version $(VERSION)

${FONTSDIR}/$(NAME)-Bold.ttf: $(BUILDDIR)/$(NAME)-Bold.ufo $(SRC)/$(NAME).fea $(FEA) $(BUILD)
	@echo "   GEN	$@"
	@$(PY) $(BUILD) --input $< --output $@ --features=$(SRC)/$(NAME).fea --version $(VERSION)

$(DOC)/Documentation-Arabic.html: $(DOC)/Documentation-Arabic.md
	@echo "   GEN	$@"
	@pandoc $< -o $@ -f markdown-smart -t html -s -c Documentation-Arabic.css

clean:
	rm -rfv $(TTF) $(HTML)

distclean: clean
	rm -rf $(DIST){,.zip}

dist: ttf pack doc
	@echo "   DIST	$(DIST)"
	@rm -rf $(DIST){,.zip}
	@install -Dm644 -t $(DIST) LICENSE
	@install -Dm644 -t $(DIST) $(TTF)
	@install -Dm644 -t $(DIST) README.md
	@install -Dm644 -t $(DIST) README-Arabic.md
	@install -Dm644 -t $(DIST) NEWS.md
	@install -Dm644 -t $(DIST) NEWS-Arabic.md
	@install -Dm644 -t $(DIST) $(HTML)
	@echo "   ZIP  $(DIST)"
	@zip -rq $(DIST).zip $(DIST)
