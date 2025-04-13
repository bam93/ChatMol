
.PHONY: info

info:
	clear
	@printf "\ninfo:: Experimentations with ChatMol\n\n"
	@printf "info:: common targets: purge, run\n\n"
	@/bin/ls -GF
	@printf "\n"
	@git status

purge:
	$(info )
	$(info info:: cleaning common clutter)
	@rm -rf __pycache__ Project-X

run:
	$(info )
	$(info info:: start up copilot)
	@( source ~/.venv/myenv/bin/activate ; \
	source ~/.secrets ; streamlit run main.py)

