
.PHONY: info

info:
	clear
	@printf "\ninfo:: Experimentations with ChatMol\n\n"
	@printf "info:: common targets: purge, copilot\n\n"
	@/bin/ls -GF
	@printf "\n"
	@git status

purge:
	$(info )
	$(info info:: cleaning common clutter)
	@(cd copilot_public ; rm -rf __pycache__ Project-X)

copilot:
	$(info )
	$(info info:: start up copilot)
	@( source ~/.venv/myenv/bin/activate ; \
	cd copilot_public ; source ~/.secrets ; streamlit run main.py)

