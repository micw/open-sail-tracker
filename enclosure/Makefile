TOOLKIT := freecad-toolkit/freecad_headless.py
GEOMETRY := geometry_h802_tray.py
REFERENCE_PREPARER := prepare_h802_reference.py
REDUCED_REFERENCE := h802_reference_reduced.brep
PACKED_REFERENCE := $(REDUCED_REFERENCE).xz

.PHONY: prepare-reference unpack-reference test clean-reference

prepare-reference:
	./$(REFERENCE_PREPARER)
	xz -9e -c $(REDUCED_REFERENCE) > $(PACKED_REFERENCE)

unpack-reference: $(REDUCED_REFERENCE)

test: unpack-reference
	$(TOOLKIT) test $(GEOMETRY)

$(REDUCED_REFERENCE): $(PACKED_REFERENCE)
	xz -d -c $(PACKED_REFERENCE) > $(REDUCED_REFERENCE)

clean-reference:
	rm -f $(REDUCED_REFERENCE)
